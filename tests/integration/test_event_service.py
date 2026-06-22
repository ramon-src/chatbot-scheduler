# tests/integration/test_event_service.py
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.calendar import Calendar
from app.models.client import Client
from app.models.event import Event, EventStatus
from app.models.user import User
from app.services.event_service import EventService

TZ = ZoneInfo("America/Sao_Paulo")
DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    # cleanup events created by this test
    session.query(Event).filter(Event.google_event_id.like("test-%")).delete(synchronize_session=False)
    session.commit()
    session.close()


def test_get_primary_calendar_creates_when_absent(db):
    svc = EventService(db)
    cal = svc.get_primary_calendar(DEV_USER_ID)
    assert cal.is_primary is True
    assert cal.google_calendar_id == "primary"


def test_record_and_list_event(db):
    svc = EventService(db)
    start = datetime(2026, 6, 22, 10, 0, tzinfo=TZ)
    end = datetime(2026, 6, 22, 11, 0, tzinfo=TZ)
    ev = svc.record_event(
        user_id=DEV_USER_ID, client_id=None, title="Sessão - Teste",
        start=start, end=end, google_event_id="test-evt-1",
    )
    assert ev.status == EventStatus.SCHEDULED.value
    found = svc.list_events_in_range(DEV_USER_ID, start, end)
    assert any(e.google_event_id == "test-evt-1" for e in found)


def test_cancel_event_sets_status(db):
    svc = EventService(db)
    start = datetime(2026, 6, 23, 10, 0, tzinfo=TZ)
    ev = svc.record_event(
        user_id=DEV_USER_ID, client_id=None, title="x",
        start=start, end=start, google_event_id="test-evt-2",
    )
    cancelled = svc.cancel_event(ev)
    assert cancelled.status == EventStatus.CANCELLED.value


def test_two_users_can_each_have_primary_calendar(db):
    """Regression: google_calendar_id='primary' is unique PER USER, not globally.
    Before the composite-unique fix this second insert raised IntegrityError."""
    second_user_id = UUID("550e8400-e29b-41d4-a716-446655440099")
    db.add(User(id=second_user_id, email="second-user-test@example.com", name="Second Test"))
    db.commit()
    try:
        EventService(db).get_primary_calendar(DEV_USER_ID)  # dev user primary
        cal2 = EventService(db).get_primary_calendar(second_user_id)  # must not collide
        assert cal2.google_calendar_id == "primary"
        assert cal2.user_id == second_user_id
    finally:
        db.query(Calendar).filter(Calendar.user_id == second_user_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == second_user_id).delete(synchronize_session=False)
        db.commit()


def test_find_client_session_on_date_late_evening_no_day_shift(db):
    """M3 regression: a session at 22:00 America/Sao_Paulo (UTC-3) must match the
    local calendar date (2026-07-07), NOT the UTC date (2026-07-08).

    Before the fix, cast(start_time, Date) operated in the DB session timezone
    (UTC), so 22:00 SP = 01:00 UTC next day → wrong date match.
    After the fix, func.timezone('America/Sao_Paulo', start_time) converts the
    timestamptz to SP local time before the date cast, so 22:00 SP → date 2026-07-07.
    """
    svc = EventService(db)
    # Seed a throwaway client
    client = Client(
        id=uuid4(), user_id=DEV_USER_ID, name="Timezone Teste",
        phone=f"+5551{uuid4().int % 1000000000:09d}", invoice_day=10,
        consult_price=Decimal("200"), is_active=True,
    )
    db.add(client)
    db.commit()

    # Single non-recurring event at 22:00 SP (UTC−3) on 2026-07-07
    # In UTC this is 2026-07-08T01:00:00Z — the old cast would have returned 2026-07-08.
    sp_start = datetime(2026, 7, 7, 22, 0, tzinfo=TZ)
    sp_end = datetime(2026, 7, 7, 23, 0, tzinfo=TZ)
    ev = svc.record_event(
        user_id=DEV_USER_ID, client_id=client.id,
        title="Sessão Noturna Timezone",
        start=sp_start, end=sp_end,
        google_event_id=f"test-tz-{uuid4().hex[:8]}",
        is_recurring=False,
    )

    try:
        # Must find the event on 2026-07-07 (SP local date), not 2026-07-08 (UTC date)
        found = svc.find_client_session_on_date(DEV_USER_ID, client.id, date(2026, 7, 7))
        assert found is not None, "Session should be found on its SP local date 2026-07-07"
        assert found.id == ev.id

        # Must NOT be found on the UTC-shifted date
        not_found = svc.find_client_session_on_date(DEV_USER_ID, client.id, date(2026, 7, 8))
        assert not_found is None, "Session must NOT appear on the UTC-shifted date 2026-07-08"
    finally:
        db.query(Event).filter(Event.id == ev.id).delete(synchronize_session=False)
        db.query(Client).filter(Client.id == client.id).delete(synchronize_session=False)
        db.commit()


def test_ensure_calendar_creates_then_updates(db):
    from app.models.calendar import Calendar
    # cleanup any pre-existing primary for a clean assertion
    db.query(Calendar).filter(Calendar.user_id == DEV_USER_ID, Calendar.is_primary == True).delete(synchronize_session=False)  # noqa: E712
    db.commit()
    svc = EventService(db)
    assert svc.get_existing_primary(DEV_USER_ID) is None
    cal = svc.ensure_calendar(DEV_USER_ID, "sa-cal-1@group.calendar.google.com", name="SimplificaPsi — Dev")
    assert cal.google_calendar_id == "sa-cal-1@group.calendar.google.com"
    assert cal.is_primary is True
    # second call updates the SAME row (no duplicate)
    cal2 = svc.ensure_calendar(DEV_USER_ID, "sa-cal-2@group.calendar.google.com")
    assert cal2.id == cal.id
    assert cal2.google_calendar_id == "sa-cal-2@group.calendar.google.com"
    # restore the default primary so other tests/seed stay consistent
    svc.ensure_calendar(DEV_USER_ID, "primary", name="Principal")
