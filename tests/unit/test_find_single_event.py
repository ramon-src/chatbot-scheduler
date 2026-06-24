"""Shared single-event finder used by cancel and reschedule."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.agents.tools.calendar_tools import _find_single_event_for_client

TZ = "America/Sao_Paulo"


def _deps(events):
    es = MagicMock()
    es.list_events_in_range.return_value = events
    es.ensure_occurrences.return_value = 0
    return SimpleNamespace(
        event_service=es, user_id=uuid4(), timezone=TZ,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )


def test_returns_the_single_matching_event():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    ev = SimpleNamespace(id=uuid4(), client_id=cid)
    event, error = _find_single_event_for_client(_deps([ev]), client, "this_week")
    assert error is None and event is ev


def test_zero_matches_returns_not_found_error():
    client = SimpleNamespace(id=uuid4(), name="Maria Silva")
    other = SimpleNamespace(id=uuid4(), client_id=uuid4())
    event, error = _find_single_event_for_client(_deps([other]), client, "this_week")
    assert event is None and error["success"] is False and "Maria" in error["message"]


def test_multiple_matches_asks_for_day():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    evs = [SimpleNamespace(id=uuid4(), client_id=cid), SimpleNamespace(id=uuid4(), client_id=cid)]
    event, error = _find_single_event_for_client(_deps(evs), client, "this_week")
    assert event is None and error["data"]["count"] == 2
