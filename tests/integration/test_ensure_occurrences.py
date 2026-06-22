# tests/integration/test_ensure_occurrences.py
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
def seeded():
    """A weekly Tuesday 09:00 series template + its client, cleaned up after."""
    db = SessionLocal()
    client = Client(
        id=uuid4(), user_id=DEV_USER_ID, name="Recorrente Teste",
        phone=f"+5551{uuid4().int % 1000000000:09d}", invoice_day=10,
        consult_price=Decimal("180"), is_active=True,
    )
    db.add(client)
    db.commit()
    svc = EventService(db)
    cal = svc.get_primary_calendar(DEV_USER_ID)
    # First Tuesday 09:00 of a fixed reference week
    start = datetime(2026, 7, 7, 9, 0, tzinfo=TZ)  # a Tuesday
    template = Event(
        id=uuid4(), user_id=DEV_USER_ID, client_id=client.id, calendar_id=cal.id,
        title="Sessão - Recorrente Teste", start_time=start, end_time=start + timedelta(hours=1),
        is_recurring=True, recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=TU",
        google_event_id=f"series-{uuid4().hex[:8]}", status=EventStatus.SCHEDULED.value,
        price=None,
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


def test_materializes_one_row_per_week(seeded):
    db, client, template, start = seeded
    svc = EventService(db)
    range_start = start
    range_end = start + timedelta(days=21)  # 3 weeks
    created = svc.ensure_occurrences(DEV_USER_ID, range_start, range_end)
    assert created == 3
    occ = db.query(Event).filter(Event.parent_event_id == template.id).order_by(Event.start_time).all()
    assert [e.occurrence_date.isoformat() for e in occ] == ["2026-07-07", "2026-07-14", "2026-07-21"]
    # price falls back to the client's consult_price; sessions are billable
    assert all(e.price == Decimal("180") for e in occ)
    assert all(e.billable is True for e in occ)
    assert all(e.parent_event_id == template.id and not e.is_recurring for e in occ)


def test_is_idempotent(seeded):
    db, client, template, start = seeded
    svc = EventService(db)
    rs, re_ = start, start + timedelta(days=21)
    svc.ensure_occurrences(DEV_USER_ID, rs, re_)
    created_again = svc.ensure_occurrences(DEV_USER_ID, rs, re_)
    assert created_again == 0
    assert db.query(Event).filter(Event.parent_event_id == template.id).count() == 3


def test_respects_until(seeded):
    db, client, template, start = seeded
    template.recurrence_rule = "RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20260715T120000Z"
    db.commit()
    svc = EventService(db)
    created = svc.ensure_occurrences(DEV_USER_ID, start, start + timedelta(days=28))
    # only 2026-07-07 and 2026-07-14 fall on/before the UNTIL
    assert created == 2


def test_concurrent_insert_swallows_integrity_error(seeded, monkeypatch):
    """Prove that an IntegrityError from a race-condition duplicate insert is
    swallowed, not propagated.

    Strategy:
    1. Pre-insert the first occurrence row via a *separate* committed session so it
       already exists in the DB.
    2. Monkeypatch `_materialized_dates` on the service instance to return an empty
       set, forcing the service to attempt a conflicting insert.
    3. Assert: (a) no exception raised, (b) returns 0, (c) DB row count unchanged.
    """
    db, client, template, start = seeded

    # Step 1: Pre-insert the first occurrence via a separate session (committed).
    from app.core.database import SessionLocal
    from app.models.event import PaymentStatus

    pre_db = SessionLocal()
    try:
        cal_id = template.calendar_id
        first_occ_date = start.date()
        pre_db.add(Event(
            id=uuid4(), user_id=DEV_USER_ID, client_id=template.client_id,
            calendar_id=cal_id, title=template.title,
            start_time=start, end_time=start + timedelta(hours=1),
            parent_event_id=template.id, occurrence_date=first_occ_date,
            is_recurring=False, google_event_id=None,
            status=EventStatus.SCHEDULED.value,
            payment_status=PaymentStatus.PENDING.value,
            price=None, billable=True,
        ))
        pre_db.commit()
    finally:
        pre_db.close()

    # Step 2: Count rows before the conflicting call.
    before = db.query(Event).filter(Event.parent_event_id == template.id).count()

    # Step 3: Monkeypatch _materialized_dates to return empty set so the service
    # thinks no occurrences exist yet, triggering a conflicting INSERT.
    svc = EventService(db)
    monkeypatch.setattr(svc, "_materialized_dates", lambda template_id: set())

    # range covers only the pre-inserted date
    range_end = start + timedelta(days=7)

    # (a) must NOT raise
    result = svc.ensure_occurrences(DEV_USER_ID, start, range_end)

    # (b) returns 0 (rolled back — the race was lost)
    assert result == 0

    # (c) DB still has the same number of rows (no duplicate, no loss)
    db.expire_all()  # ensure fresh read after rollback
    after = db.query(Event).filter(Event.parent_event_id == template.id).count()
    assert after == before
