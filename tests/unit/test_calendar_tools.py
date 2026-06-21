# tests/unit/test_calendar_tools.py
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.deps import AgentDeps
from app.agents.tools.calendar_tools import (
    create_event_impl,
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
