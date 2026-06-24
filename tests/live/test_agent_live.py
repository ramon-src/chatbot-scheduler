"""End-to-end functional tests against the REAL LLM + real Google Calendar.

Skipped unless RUN_LIVE=1 and the required credentials are present. Run with:

    make test-live          # RUN_LIVE=1 uv run pytest -m live -s -v

These tests cost LLM tokens and create/delete real Google Calendar events under
the service account. They use an isolated test user (see tests/live/conftest.py)
and clean up after themselves.

Assertions read the TOOL return values from the agent's message history (what
*our* code produced), not the LLM's free-text rephrasing — so they are
deterministic about behavior (e.g. timezone formatting) while still routing
tool selection through the real LLM.

The broader scenario backlog lives in test_agent_live_scenarios.py (skipped,
to be enabled/implemented later).
"""

import logging
from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.live

# Quiet the very chatty HTTP/Google debug logs so the test output stays readable.
for _noisy in ("httpx", "httpcore", "openai", "google_auth_httplib2", "googleapiclient"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


async def test_schedule_creates_event_at_local_time(live):
    from app.models.event import Event

    tomorrow = (datetime.now(live.tz) + timedelta(days=1)).date()
    result = await live.send(f"agenda a {live.client_name} amanhã às 10h")

    creates = live.tool_returns(result, "create_event")
    assert creates, f"create_event was not called. Output: {result.output!r}"
    assert creates[-1]["success"] is True, creates[-1]

    ev = (
        live.db.query(Event)
        .filter(Event.user_id == live.user_id, Event.status != "cancelled")
        .order_by(Event.created_at.desc())
        .first()
    )
    assert ev is not None, "no Event row persisted"
    assert ev.google_event_id, "event was not created on Google (no google_event_id)"
    local = ev.start_time.astimezone(live.tz)
    assert local.date() == tomorrow
    assert local.hour == 10, f"expected 10h local, got {local.isoformat()}"


async def test_recurring_weekly_event(live):
    """'sessão semanal toda terça às 9h' → create_recurring_event with a weekly RRULE."""
    from app.models.event import Event

    result = await live.send(f"marca uma sessão semanal com a {live.client_name} toda terça às 9h")
    recs = live.tool_returns(result, "create_recurring_event")
    assert recs, f"create_recurring_event was not called. Output: {result.output!r}"
    assert recs[-1]["success"] is True, recs[-1]

    ev = (
        live.db.query(Event)
        .filter(Event.user_id == live.user_id, Event.is_recurring == True)  # noqa: E712
        .order_by(Event.created_at.desc())
        .first()
    )
    assert ev is not None and ev.google_event_id, "recurring event not persisted/created on Google"
    assert "FREQ=WEEKLY" in (ev.recurrence_rule or ""), ev.recurrence_rule
    assert ev.start_time.astimezone(live.tz).hour == 9


async def test_list_shows_local_time(live):
    """Regression for the UTC display bug: the list tool message must say 10h, not 13h."""
    result = await live.send("o que eu tenho para amanhã?")

    lists = live.tool_returns(result, "list_events")
    assert lists, f"list_events was not called. Output: {result.output!r}"
    msg = lists[-1]["message"]
    assert "10h" in msg, f"expected local 10h in tool message, got: {msg!r}"
    assert "13h" not in msg, f"event leaked in UTC: {msg!r}"


async def test_unknown_client_is_rejected(live):
    from app.models.event import Event

    before = live.db.query(Event).filter(Event.user_id == live.user_id).count()
    result = await live.send("agenda o Carlos Inexistente Mendes amanhã às 16h")

    creates = live.tool_returns(result, "create_event")
    # Either the tool was not called, or it was called and returned success=False.
    if creates:
        assert creates[-1]["success"] is False, "scheduled an event for a non-existent client"
    after = live.db.query(Event).filter(Event.user_id == live.user_id).count()
    assert after == before, "an orphan event was created for an unknown client"


async def test_remembers_client_across_turns(live):
    """Multi-turn memory: turn 2 says 'dela' — the agent must resolve it to the
    client named in turn 1 via replayed history (no clarifying question)."""
    await live.send_memory(f"tenho uma cliente chamada {live.client_name}, tudo bem?")
    result = await live.send_memory("me lembra o telefone dela?")

    # If memory worked, the agent looked up Maria (resolving 'dela') and returned her phone.
    finds = live.tool_returns(result, "find_client")
    assert finds, f"agent did not resolve 'dela' from history. Output: {result.output!r}"
    assert any(
        (f.get("data") or {}).get("phone") == live.client_phone for f in finds if f.get("success")
    ), f"find_client did not resolve to {live.client_name}: {finds}"


async def test_cancel_removes_event(live):
    from app.models.event import Event

    result = await live.send(f"cancela a sessão da {live.client_name} amanhã")
    cancels = live.tool_returns(result, "cancel_event")
    assert cancels, f"cancel_event was not called. Output: {result.output!r}"
    assert cancels[-1]["success"] is True, cancels[-1]

    # Scope the check to tomorrow: other tests in this module create events on
    # other days (e.g. the weekly recurring one), so a global count would be wrong.
    tomorrow = (datetime.now(live.tz) + timedelta(days=1)).date()
    active_tomorrow = [
        e for e in live.db.query(Event).filter(
            Event.user_id == live.user_id, Event.status != "cancelled"
        )
        if e.start_time.astimezone(live.tz).date() == tomorrow
    ]
    assert active_tomorrow == [], "tomorrow's event was not cancelled in the Postgres mirror"
