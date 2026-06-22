"""Postgres dual-write for agenda events (Google Calendar is source of truth)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.calendar import Calendar
from app.models.event import Event, EventStatus


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

    def cancel_event(self, event: Event) -> Event:
        event.status = EventStatus.CANCELLED.value
        self.db.commit()
        self.db.refresh(event)
        return event
