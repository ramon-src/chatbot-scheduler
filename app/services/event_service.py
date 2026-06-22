"""Postgres dual-write for agenda events (Google Calendar is source of truth)."""

from datetime import date, datetime, timedelta  # noqa: F401
from uuid import UUID

from dateutil.rrule import rrulestr
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.calendar import Calendar
from app.models.client import Client
from app.models.event import Event, EventStatus, PaymentStatus


class EventService:
    def __init__(self, db: Session):
        self.db = db

    def get_primary_calendar(self, user_id: UUID) -> Calendar:
        cal = self.get_existing_primary(user_id)
        if cal is None:
            cal = Calendar(
                user_id=user_id, name="Principal",
                google_calendar_id="primary", is_primary=True, is_active=True,
            )
            self.db.add(cal)
            self.db.commit()
            self.db.refresh(cal)
        return cal

    def get_existing_primary(self, user_id: UUID) -> Calendar | None:
        return self.db.query(Calendar).filter(
            and_(Calendar.user_id == user_id, Calendar.is_primary == True)  # noqa: E712
        ).first()

    def ensure_calendar(self, user_id: UUID, google_calendar_id: str, name: str = "Principal") -> Calendar:
        """Upsert the user's primary calendar row with the real google_calendar_id."""
        cal = self.get_existing_primary(user_id)
        if cal is None:
            cal = Calendar(
                user_id=user_id, name=name, google_calendar_id=google_calendar_id,
                is_primary=True, is_active=True,
            )
            self.db.add(cal)
        else:
            cal.google_calendar_id = google_calendar_id
            cal.name = name
        self.db.commit()
        self.db.refresh(cal)
        return cal

    def record_event(
        self, *, user_id: UUID, client_id, title: str, start: datetime, end: datetime,
        google_event_id: str, is_recurring: bool = False, recurrence_rule=None, price=None,
    ) -> Event:
        calendar = self.get_primary_calendar(user_id)
        event = Event(
            user_id=user_id, client_id=client_id, calendar_id=calendar.id,
            title=title, start_time=start, end_time=end,
            google_event_id=google_event_id, is_recurring=is_recurring,
            recurrence_rule=recurrence_rule, price=price,
            status=EventStatus.SCHEDULED.value,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_events_in_range(self, user_id: UUID, start: datetime, end: datetime) -> list[Event]:
        return self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.start_time >= start,
                Event.start_time < end,
                Event.status != EventStatus.CANCELLED.value,
                # exclude series templates (the expansion source is not a session)
                ~and_(Event.is_recurring == True, Event.parent_event_id.is_(None)),  # noqa: E712
            )
        ).order_by(Event.start_time).all()

    def find_by_google_event_id(self, user_id: UUID, google_event_id: str) -> Event | None:
        return self.db.query(Event).filter(
            and_(Event.user_id == user_id, Event.google_event_id == google_event_id)
        ).first()

    def update_event(self, event: Event, *, title=None, start=None, end=None) -> Event:
        if title is not None:
            event.title = title
        if start is not None:
            event.start_time = start
        if end is not None:
            event.end_time = end
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_event(self, event_id) -> Event | None:
        return self.db.get(Event, event_id)

    def cancel_event(self, event: Event, billable: bool | None = None) -> Event:
        event.status = EventStatus.CANCELLED.value
        if billable is not None:
            event.billable = billable
        self.db.commit()
        self.db.refresh(event)
        return event

    def _series_templates(self, user_id: UUID) -> list[Event]:
        return self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.is_recurring == True,  # noqa: E712
                Event.parent_event_id.is_(None),
                Event.status != EventStatus.CANCELLED.value,
            )
        ).all()

    def ensure_occurrences(self, user_id: UUID, range_start: datetime, range_end: datetime) -> int:
        """Idempotently materialize per-occurrence rows for the user's recurring
        series within [range_start, range_end]. Returns the number created."""
        created = 0
        for template in self._series_templates(user_id):
            rule_text = (template.recurrence_rule or "").removeprefix("RRULE:")
            if not rule_text:
                continue
            rule = rrulestr(rule_text, dtstart=template.start_time)
            duration = template.end_time - template.start_time
            existing = {
                row.occurrence_date
                for row in self.db.query(Event.occurrence_date).filter(
                    Event.parent_event_id == template.id
                )
            }
            client = self.db.get(Client, template.client_id) if template.client_id else None
            fallback_price = client.consult_price if client is not None else None
            for occ_start in rule.between(range_start, range_end, inc=True):
                if occ_start >= range_end:
                    continue
                occ_date = occ_start.date()
                if occ_date in existing:
                    continue
                self.db.add(Event(
                    user_id=user_id, client_id=template.client_id,
                    calendar_id=template.calendar_id, title=template.title,
                    start_time=occ_start, end_time=occ_start + duration,
                    parent_event_id=template.id, occurrence_date=occ_date,
                    is_recurring=False, google_event_id=None,
                    status=EventStatus.SCHEDULED.value,
                    payment_status=PaymentStatus.PENDING.value,
                    price=template.price if template.price is not None else fallback_price,
                    billable=True,
                ))
                existing.add(occ_date)
                created += 1
        if created:
            self.db.commit()
        return created
