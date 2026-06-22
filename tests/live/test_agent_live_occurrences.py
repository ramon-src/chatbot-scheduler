"""Live end-to-end tests for slice 3a (occurrence materialization + billable),
driven through the REAL agent (real LLM + real Google Calendar).

Skipped unless RUN_LIVE=1 and credentials are present. Run with:

    make test-live

Assertions read the actual TOOL return values and the Postgres mirror (what *our*
code did), so they are deterministic about behavior while routing tool selection
through the real LLM.

Test order matters (module-scoped fixture, shared state): the single-session
charge tests run BEFORE the recurring test so a recurring occurrence can never
make a single-day cancel ambiguous.
"""

import logging
from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.live

for _noisy in ("httpx", "httpcore", "openai", "google_auth_httplib2", "googleapiclient"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


async def test_cancel_with_charge_keeps_session_billable(live):
    """'cancela ... mas pode cobrar mesmo assim' → cancel_event(charge=True);
    the session is cancelled but stays billable."""
    from app.models.event import Event

    await live.send(
        f"agenda a {live.client_name} (telefone {live.client_phone}) amanhã às 15h, pode agendar direto"
    )
    result = await live.send(
        f"cancela a sessão de amanhã da {live.client_name}, telefone {live.client_phone}. "
        f"É ela mesma, mas pode cobrar mesmo assim."
    )
    cancels = live.tool_returns(result, "cancel_event")
    assert cancels, f"cancel_event was not called. Output: {result.output!r}"
    assert cancels[-1]["success"] is True, cancels[-1]

    tomorrow = (datetime.now(live.tz) + timedelta(days=1)).date()
    cancelled_tomorrow = [
        e for e in live.db.query(Event).filter(
            Event.user_id == live.user_id, Event.status == "cancelled"
        )
        if e.start_time.astimezone(live.tz).date() == tomorrow
    ]
    assert cancelled_tomorrow, "no cancelled event found for tomorrow"
    assert any(e.billable is True for e in cancelled_tomorrow), \
        "charge-on-cancel did not keep the session billable"


async def test_set_session_charge_waives_a_session(live):
    """'não vou cobrar a sessão ... do dia X' → set_session_charge(charge=False);
    the session's billable flag flips to False."""
    from app.models.event import Event

    day = (datetime.now(live.tz) + timedelta(days=2)).date()
    await live.send(
        f"agenda a {live.client_name} (telefone {live.client_phone}) dia {day.isoformat()} às 16h, "
        f"pode agendar direto"
    )
    result = await live.send(
        f"não vou cobrar a sessão da {live.client_name}, telefone {live.client_phone}, "
        f"do dia {day.isoformat()}. É ela mesma."
    )
    sets = live.tool_returns(result, "set_session_charge")
    assert sets, f"set_session_charge was not called. Output: {result.output!r}"
    assert sets[-1]["success"] is True, sets[-1]

    on_day = [
        e for e in live.db.query(Event).filter(Event.user_id == live.user_id)
        if e.start_time.astimezone(live.tz).date() == day
    ]
    assert on_day, "no session found on the target day"
    assert any(e.billable is False for e in on_day), \
        "set_session_charge did not mark the session non-billable"


async def test_recurring_occurrence_materializes_and_lists(live):
    """A weekly series, once listed for a later week, materializes a per-occurrence
    row (parent_event_id set) — proving recurring sessions are now individually
    tracked, not a single series row."""
    from app.models.event import Event

    r1 = await live.send(
        f"A {live.client_name} já é minha cliente cadastrada. "
        f"Marca uma sessão semanal com ela toda terça às 9h, pode agendar direto."
    )
    recs = live.tool_returns(r1, "create_recurring_event")
    assert recs, f"create_recurring_event was not called. Output: {r1.output!r}"
    assert recs[-1]["success"] is True, recs[-1]

    r2 = await live.send("o que eu tenho na próxima semana?")
    lists = live.tool_returns(r2, "list_events")
    assert lists, f"list_events was not called. Output: {r2.output!r}"

    occ = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.parent_event_id.isnot(None)
    ).all()
    assert occ, "no occurrence rows were materialized by listing the agenda"
    assert all(not o.is_recurring for o in occ), "occurrence rows must not be templates"
    assert all(o.occurrence_date is not None for o in occ)
