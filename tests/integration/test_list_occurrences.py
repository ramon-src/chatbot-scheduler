from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.event import Event, EventStatus
from app.services.event_service import EventService

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def weekly_series():
    db = SessionLocal()
    client = Client(
        id=uuid4(), user_id=DEV_USER_ID, name="Lista Recorrente",
        phone=f"+5551{uuid4().int % 1000000000:09d}", invoice_day=5,
        consult_price=Decimal("150"), is_active=True,
    )
    db.add(client)
    db.commit()
    svc = EventService(db)
    cal = svc.get_primary_calendar(DEV_USER_ID)
    start = datetime(2026, 7, 7, 9, 0, tzinfo=TZ)
    template = Event(
        id=uuid4(), user_id=DEV_USER_ID, client_id=client.id, calendar_id=cal.id,
        title="Sessão - Lista Recorrente", start_time=start, end_time=start + timedelta(hours=1),
        is_recurring=True, recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=TU",
        google_event_id=f"series-{uuid4().hex[:8]}", status=EventStatus.SCHEDULED.value,
    )
    db.add(template)
    db.commit()
    yield db, client, template, start
    db.query(Event).filter(
        (Event.id == template.id) | (Event.parent_event_id == template.id)
    ).delete(synchronize_session=False)
    db.query(Client).filter(Client.id == client.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_template_row_excluded_in_its_own_week(weekly_series):
    """Template falls inside the queried window — filter must hide it, showing only the occurrence."""
    db, client, template, start = weekly_series
    svc = EventService(db)
    window_end = start + timedelta(days=1)
    svc.ensure_occurrences(DEV_USER_ID, start, window_end)
    rows = svc.list_events_in_range(DEV_USER_ID, start, window_end)
    # Without the ~and_ filter this returns 2 rows (template + occurrence); with it, exactly 1.
    assert len(rows) == 1
    assert rows[0].parent_event_id == template.id, "returned row must be the occurrence, not the template"
    assert template.id not in [r.id for r in rows], "template must be excluded from the listing"


def test_series_appears_in_later_weeks_and_template_hidden(weekly_series):
    db, client, template, start = weekly_series
    svc = EventService(db)
    # week 2 window
    w2_start = start + timedelta(days=7)
    svc.ensure_occurrences(DEV_USER_ID, w2_start, w2_start + timedelta(days=1))
    rows = svc.list_events_in_range(DEV_USER_ID, w2_start, w2_start + timedelta(days=1))
    # the occurrence shows; the template (is_recurring + no parent) does not
    assert len(rows) == 1
    assert rows[0].parent_event_id == template.id
    assert all(not (r.is_recurring and r.parent_event_id is None) for r in rows)
