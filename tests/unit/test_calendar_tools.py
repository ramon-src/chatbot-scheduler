# tests/unit/test_calendar_tools.py
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.agents.deps import AgentDeps
from app.agents.tools.calendar_tools import (
    _not_connected,
    cancel_event_impl,
    create_event_impl,
    create_recurring_event_impl,
    list_events_impl,
)

TZ = ZoneInfo("America/Sao_Paulo")


def _client(name="Maria Silva", phone="+5551981321543"):
    return SimpleNamespace(id=uuid4(), name=name, phone=phone)


def _deps(*, calendar_service=None, event_service=None, client_by_phone=None, client_by_name=None):
    cs = MagicMock()
    cs.find_client_by_phone = AsyncMock(return_value=client_by_phone)
    cs.find_client_by_name = AsyncMock(return_value=client_by_name or [])
    return AgentDeps(
        db=MagicMock(), user_id=uuid4(), user_name="Dr. Ana",
        current_datetime=datetime(2026, 6, 21, 9, 0, tzinfo=TZ),
        timezone="America/Sao_Paulo", history_summary=None,
        client_service=cs, calendar_service=calendar_service, event_service=event_service,
    )


async def test_create_event_requires_connected_calendar():
    deps = _deps(calendar_service=None)
    out = await create_event_impl(
        deps, client_phone="+5551981321543", start_time=datetime(2026, 6, 22, 10, tzinfo=TZ)
    )
    assert out["success"] is False
    assert "Google Agenda" in out["message"]


async def test_create_event_requires_existing_client():
    cal = MagicMock()
    deps = _deps(calendar_service=cal, event_service=MagicMock(), client_by_phone=None)
    out = await create_event_impl(
        deps, client_phone="+5551999999999", start_time=datetime(2026, 6, 22, 10, tzinfo=TZ)
    )
    assert out["success"] is False
    assert "cadastr" in out["message"].lower()
    cal.create_event.assert_not_called()


async def test_create_event_happy_path_dual_writes():
    cal = MagicMock()
    cal.create_event.return_value = {"id": "gevt-1", "html_link": "https://x"}
    es = MagicMock()
    es.record_event.return_value = SimpleNamespace(id=uuid4(), google_event_id="gevt-1")
    deps = _deps(calendar_service=cal, event_service=es, client_by_phone=_client())
    out = await create_event_impl(
        deps, client_phone="+5551981321543",
        start_time=datetime(2026, 6, 22, 10, 0, tzinfo=TZ), duration_minutes=50,
    )
    assert out["success"] is True
    assert "Maria" in out["message"]
    assert "gevt-1" not in out["message"]  # no IDs leaked
    # dual write happened
    cal.create_event.assert_called_once()
    es.record_event.assert_called_once()
    # end = start + 50min
    kwargs = cal.create_event.call_args.kwargs
    assert (kwargs["end"] - kwargs["start"]).total_seconds() == 50 * 60


async def test_list_events_empty_period():
    es = MagicMock()
    es.list_events_in_range.return_value = []
    deps = _deps(calendar_service=MagicMock(), event_service=es)
    out = await list_events_impl(deps, period="today")
    assert out["success"] is True
    assert out["data"]["total"] == 0


async def test_create_event_compensates_google_when_local_write_fails():
    """If the Postgres write throws after the Google event is created, the orphan
    Google event must be rolled back and the tool must degrade gracefully (no raise)."""
    cal = MagicMock()
    cal.create_event.return_value = {"id": "orphan-1", "html_link": "u"}
    es = MagicMock()
    es.record_event.side_effect = RuntimeError("db down")
    deps = _deps(calendar_service=cal, event_service=es, client_by_phone=_client())
    out = await create_event_impl(
        deps, client_phone="+5551981321543", start_time=datetime(2026, 6, 22, 10, tzinfo=TZ)
    )
    assert out["success"] is False
    assert "orphan-1" not in out["message"]
    cal.cancel_event.assert_called_once_with("orphan-1")  # compensated


async def test_recurring_event_dual_writes_with_rrule():
    cal = MagicMock()
    cal.build_weekly_rrule.return_value = "RRULE:FREQ=WEEKLY;BYDAY=TU"
    cal.create_event.return_value = {"id": "rec-1", "html_link": "u"}
    es = MagicMock()
    deps = _deps(calendar_service=cal, event_service=es, client_by_phone=_client())
    out = await create_recurring_event_impl(
        deps, client_phone="+5551981321543",
        start_time=datetime(2026, 6, 23, 10, 0, tzinfo=TZ), weekdays=["TU"],
    )
    assert out["success"] is True
    assert "rec-1" not in out["message"]  # no IDs leaked
    # recurrence passed through to GCal and persisted locally
    assert cal.create_event.call_args.kwargs["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=TU"]
    assert es.record_event.call_args.kwargs["is_recurring"] is True


async def test_recurring_event_requires_existing_client():
    cal = MagicMock()
    deps = _deps(calendar_service=cal, event_service=MagicMock(), client_by_phone=None)
    out = await create_recurring_event_impl(
        deps, client_phone="+5551999999999", start_time=datetime(2026, 6, 23, 10, tzinfo=TZ)
    )
    assert out["success"] is False
    cal.create_event.assert_not_called()  # no orphan recurring event


async def test_cancel_event_ambiguous_period_cancels_nothing():
    client = _client()
    e1 = SimpleNamespace(client_id=client.id, google_event_id="g1", title="Sessão - Maria Silva")
    e2 = SimpleNamespace(client_id=client.id, google_event_id="g2", title="Sessão - Maria Silva")
    cal = MagicMock()
    es = MagicMock()
    es.list_events_in_range.return_value = [e1, e2]
    deps = _deps(calendar_service=cal, event_service=es, client_by_phone=client)
    out = await cancel_event_impl(deps, client_phone=client.phone, period="this_week")
    assert out["success"] is False
    cal.cancel_event.assert_not_called()
    es.cancel_event.assert_not_called()


async def test_cancel_event_filters_to_this_client_and_cancels_both_sides():
    client = _client()
    other = SimpleNamespace(client_id=uuid4(), google_event_id="other", title="x")
    mine = SimpleNamespace(client_id=client.id, google_event_id="g-mine", title="Sessão - Maria Silva")
    cal = MagicMock()
    es = MagicMock()
    es.list_events_in_range.return_value = [other, mine]  # only `mine` belongs to client
    deps = _deps(calendar_service=cal, event_service=es, client_by_phone=client)
    out = await cancel_event_impl(deps, client_phone=client.phone, period="this_week")
    assert out["success"] is True
    cal.cancel_event.assert_called_once_with("g-mine")
    es.cancel_event.assert_called_once_with(mine)


def test_not_connected_returns_fresh_dict():
    """Regression: each call must return an independent dict, not a shared mutable constant."""
    a = _not_connected()
    a["data"] = "mutated"
    b = _not_connected()
    assert b["data"] is None
