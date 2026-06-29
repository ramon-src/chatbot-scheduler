"""EventService billing helpers: list pending, set paid."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.calendar import Calendar
from app.models.client import Client
from app.models.event import Event, EventStatus, PaymentStatus
from app.services.event_service import EventService

TZ = ZoneInfo("America/Sao_Paulo")
DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def seed_user_client_calendar():
    """Seed a client and return (db, user_id, client, calendar), cleaned up after."""
    db = SessionLocal()
    client = Client(
        id=uuid4(), user_id=DEV_USER_ID, name="Billing Teste",
        phone=f"+5551{uuid4().int % 1000000000:09d}", invoice_day=10,
        consult_price=Decimal("200"), is_active=True,
    )
    db.add(client)
    db.commit()
    svc = EventService(db)
    calendar = svc.get_primary_calendar(DEV_USER_ID)
    yield db, DEV_USER_ID, client, calendar
    # cleanup events and client created by this test
    db.query(Event).filter(Event.client_id == client.id).delete(synchronize_session=False)
    db.query(Client).filter(Client.id == client.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_list_pending_excludes_future_paid_and_nonbillable(seed_user_client_calendar):
    db, user_id, client, calendar = seed_user_client_calendar
    es = EventService(db)
    now = datetime(2026, 6, 29, 12, 0, tzinfo=TZ)

    def _ev(hours_ago, *, paid=False, billable=True):
        start = now - timedelta(hours=hours_ago)
        e = Event(user_id=user_id, client_id=client.id, calendar_id=calendar.id,
                  title="Sessão", start_time=start, end_time=start + timedelta(hours=1),
                  price=Decimal("200"), billable=billable,
                  status=EventStatus.SCHEDULED.value,
                  payment_status=(PaymentStatus.PAID.value if paid else PaymentStatus.PENDING.value))
        db.add(e)
        return e

    past_pending = _ev(48)
    _ev(24, paid=True)            # paid -> excluded
    _ev(24, billable=False)       # non-billable -> excluded
    future = Event(user_id=user_id, client_id=client.id, calendar_id=calendar.id,
                   title="Futura", start_time=now + timedelta(hours=24),
                   end_time=now + timedelta(hours=25), price=Decimal("200"),
                   billable=True, status=EventStatus.SCHEDULED.value,
                   payment_status=PaymentStatus.PENDING.value)
    db.add(future)
    db.commit()

    pending = es.list_pending_payments(user_id, client_id=client.id, now=now)
    ids = {e.id for e in pending}
    assert past_pending.id in ids
    assert future.id not in ids
    assert len(pending) == 1

    es.set_payment_status(past_pending, PaymentStatus.PAID.value)
    db.refresh(past_pending)
    assert past_pending.payment_status == PaymentStatus.PAID.value
    assert es.list_pending_payments(user_id, client_id=client.id, now=now) == []
