"""reschedule_series moves the template and clears future materialized occurrences."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.event import Event, EventStatus
from app.services.event_service import EventService

TZ = ZoneInfo("America/Sao_Paulo")
DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def seed_user_client_calendar():
    """Seed a client and return (user_id, client, calendar), cleaned up after."""
    db = SessionLocal()
    client = Client(
        id=uuid4(), user_id=DEV_USER_ID, name="Série Teste",
        phone=f"+5551{uuid4().int % 1000000000:09d}", invoice_day=10,
        consult_price=Decimal("200"), is_active=True,
    )
    db.add(client)
    db.commit()
    svc = EventService(db)
    calendar = svc.get_primary_calendar(DEV_USER_ID)
    yield db, DEV_USER_ID, client, calendar
    db.query(Client).filter(Client.id == client.id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_reschedule_series_updates_template_and_drops_future(seed_user_client_calendar):
    db, user_id, client, calendar = seed_user_client_calendar
    es = EventService(db)
    start = datetime(2026, 6, 23, 10, 0, tzinfo=TZ)
    template = es.record_event(
        user_id=user_id, client_id=client.id, title="Sessão - X",
        start=start, end=start + timedelta(minutes=60), google_event_id="g-series",
        is_recurring=True, recurrence_rule="RRULE:FREQ=WEEKLY;BYDAY=TU",
    )
    # a future materialized occurrence
    future = Event(
        user_id=user_id, client_id=client.id, calendar_id=calendar.id, title="Sessão - X",
        start_time=start + timedelta(days=7), end_time=start + timedelta(days=7, minutes=60),
        parent_event_id=template.id, occurrence_date=(start + timedelta(days=7)).date(),
        status=EventStatus.SCHEDULED.value,
    )
    db.add(future)
    db.commit()

    new_start = datetime(2026, 6, 23, 15, 0, tzinfo=TZ)
    es.reschedule_series(template, new_start, new_start + timedelta(minutes=60),
                         from_dt=datetime(2026, 6, 23, 9, 0, tzinfo=TZ))

    db.refresh(template)
    assert template.start_time.astimezone(TZ).hour == 15
    remaining = db.query(Event).filter(Event.parent_event_id == template.id).count()
    assert remaining == 0
    # cleanup template (client cleanup is in fixture)
    db.query(Event).filter(
        (Event.id == template.id) | (Event.parent_event_id == template.id)
    ).delete(synchronize_session=False)
    db.commit()
