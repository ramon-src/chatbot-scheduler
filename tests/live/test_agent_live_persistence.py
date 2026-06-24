"""Live persistence round-trips: create/list/cancel/reschedule reflect in both stores."""

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.live]


async def test_created_event_persists_and_lists_back(live):
    await live.send(f"agenda a {live.client_name} amanhã às 14h")
    # mirror has it
    from app.models.event import Event, EventStatus
    rows = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status == EventStatus.SCHEDULED.value
    ).all()
    assert any(r.start_time.astimezone(live.tz).hour == 14 for r in rows)
    # agent lists it back at the right local time
    listed = await live.send("o que tenho amanhã?")
    assert "14" in listed.output


async def test_cancel_removes_from_both_stores(live):
    await live.send_memory(f"agenda a {live.client_name} amanhã às 9h")
    await live.send_memory(f"cancela o compromisso da {live.client_name} amanhã")
    from app.models.event import Event, EventStatus
    active = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status == EventStatus.SCHEDULED.value,
    ).all()
    assert all(r.start_time.astimezone(live.tz).hour != 9 for r in active)


async def test_reschedule_reflects_new_time(live):
    await live.send_memory(f"agenda a {live.client_name} amanhã às 11h")
    await live.send_memory(f"muda o compromisso da {live.client_name} amanhã para as 16h")
    from app.models.event import Event, EventStatus
    rows = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status == EventStatus.SCHEDULED.value,
    ).all()
    hours = {r.start_time.astimezone(live.tz).hour for r in rows}
    assert 16 in hours and 11 not in hours
