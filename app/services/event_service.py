"""Postgres dual-write for agenda events (Google Calendar is source of truth)."""

from datetime import date, datetime, timedelta  # noqa: F401
from uuid import UUID

from dateutil.rrule import rrulestr
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
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

    def find_client_session_on_date(self, user_id: UUID, client_id, day: date) -> Event | None:
        from sqlalchemy import Date as SqlDate
        from sqlalchemy import cast, func
        return self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.client_id == client_id,
                Event.status != EventStatus.CANCELLED.value,
                ~and_(Event.is_recurring == True, Event.parent_event_id.is_(None)),  # noqa: E712
                or_(
                    Event.occurrence_date == day,
                    cast(func.timezone('America/Sao_Paulo', Event.start_time), SqlDate) == day,
                ),
            )
        ).order_by(Event.start_time).first()

    def reschedule_series(self, template: Event, new_start: datetime, new_end: datetime, *, from_dt: datetime) -> Event:
        """Move a recurring series to a new time-of-day: update the template's
        start/end (the materialization dtstart) and drop future still-scheduled
        occurrences so they re-materialize from the new template. Weekday cadence
        (the RRULE BYDAY) is preserved."""
        template.start_time = new_start
        template.end_time = new_end
        self.db.query(Event).filter(
            and_(
                Event.parent_event_id == template.id,
                Event.status == EventStatus.SCHEDULED.value,
                Event.start_time >= from_dt,
            )
        ).delete(synchronize_session=False)
        self.db.commit()
        self.db.refresh(template)
        return template

    def set_payment_status(self, event: Event, status: str) -> Event:
        event.payment_status = status
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_pending_payments(self, user_id: UUID, *, client_id=None, start=None, end=None, now) -> list[Event]:
        """Billable, not-yet-paid sessions that have already occurred (start_time < now).
        Excludes cancelled-status only if non-billable; a billable cancelled no-show still
        counts. Excludes series templates."""
        q = self.db.query(Event).filter(
            and_(
                Event.user_id == user_id,
                Event.billable == True,  # noqa: E712
                Event.payment_status.in_([PaymentStatus.PENDING.value, PaymentStatus.PARTIAL.value]),
                Event.start_time < now,
                ~and_(Event.is_recurring == True, Event.parent_event_id.is_(None)),  # noqa: E712
            )
        )
        if client_id is not None:
            q = q.filter(Event.client_id == client_id)
        if start is not None:
            q = q.filter(Event.start_time >= start)
        if end is not None:
            q = q.filter(Event.start_time < end)
        return q.order_by(Event.start_time).all()

    def set_billable(self, event: Event, value: bool) -> Event:
        event.billable = value
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

    def _materialized_dates(self, template_id) -> set:
        """Return the set of occurrence_date values already persisted for a template."""
        return {
            row.occurrence_date
            for row in self.db.query(Event.occurrence_date).filter(
                Event.parent_event_id == template_id
            )
        }

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
            existing = self._materialized_dates(template.id)
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
            try:
                self.db.commit()
            except IntegrityError:
                # A concurrent materialization won the race; the occurrences now
                # exist. Roll back our losing insert batch and report none created.
                self.db.rollback()
                return 0
        return created
