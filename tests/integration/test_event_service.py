# tests/integration/test_event_service.py
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.calendar import Calendar
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
