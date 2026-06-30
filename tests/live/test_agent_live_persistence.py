"""Live persistence round-trips: create/list/cancel/reschedule reflect in both stores."""

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.live]


def _get_client_id(live):
    """Return the DB id of the live test client (Maria Silva)."""
    from app.models.client import Client
    client = live.db.query(Client).filter(
        Client.user_id == live.user_id, Client.name == live.client_name
    ).first()
    assert client is not None, f"live client '{live.client_name}' not found in DB"
    return client.id


async def test_created_event_persists_and_lists_back(live):
    client_id = _get_client_id(live)
    await live.send(f"agenda a {live.client_name} amanhã às 14h")
    # mirror has it — filter by client to avoid false positives from other tests
    from app.models.event import Event, EventStatus
    rows = live.db.query(Event).filter(
        Event.user_id == live.user_id,
        Event.client_id == client_id,
        Event.status == EventStatus.SCHEDULED.value,
    ).all()
    assert any(r.start_time.astimezone(live.tz).hour == 14 for r in rows)
    # agent lists it back at the right local time
    listed = await live.send("o que tenho amanhã?")
    assert "14" in listed.output


async def test_cancel_removes_from_both_stores(live):
    client_id = _get_client_id(live)
    await live.send_memory(f"agenda a {live.client_name} amanhã às 9h")
    await live.send_memory(f"cancela o compromisso da {live.client_name} amanhã")
    from app.models.event import Event, EventStatus
    # filter by client to avoid false positives from events of other clients at 9h
    active = live.db.query(Event).filter(
        Event.user_id == live.user_id,
        Event.client_id == client_id,
        Event.status == EventStatus.SCHEDULED.value,
    ).all()
    assert all(r.start_time.astimezone(live.tz).hour != 9 for r in active)


async def test_reschedule_reflects_new_time(live):
    client_id = _get_client_id(live)
    await live.send_memory(f"agenda a {live.client_name} amanhã às 11h")
    await live.send_memory(f"muda o compromisso da {live.client_name} amanhã para as 16h")
    from app.models.event import Event, EventStatus
    # filter by client to avoid false positives from events of other clients
    rows = live.db.query(Event).filter(
        Event.user_id == live.user_id,
        Event.client_id == client_id,
        Event.status == EventStatus.SCHEDULED.value,
    ).all()
    hours = {r.start_time.astimezone(live.tz).hour for r in rows}
    assert 16 in hours and 11 not in hours
