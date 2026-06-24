"""Conflict detection: overlap helper + warn-not-block on create."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.calendar_tools import _find_overlaps, create_event_impl

TZ = "America/Sao_Paulo"


def _ev(start, end, client_name="Maria Silva"):
    return SimpleNamespace(
        id=uuid4(), start_time=start, end_time=end,
        client=SimpleNamespace(name=client_name), client_id=uuid4(),
    )


def _deps(events, *, client=None):
    es = MagicMock()
    es.list_events_in_range.return_value = events
    es.ensure_occurrences.return_value = 0
    cs = MagicMock()

    async def _by_name(name, user_id):
        return [client] if client else []

    async def _by_phone(phone, user_id):
        return client

    cs.find_client_by_name = _by_name
    cs.find_client_by_phone = _by_phone
    return SimpleNamespace(
        event_service=es, client_service=cs, calendar_service=MagicMock(),
        user_id=uuid4(), timezone=TZ, default_consult_minutes=60,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )


def test_find_overlaps_detects_overlapping_interval():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60))
    deps = _deps([existing])
    hits = _find_overlaps(deps, base + timedelta(minutes=30), base + timedelta(minutes=90))
    assert len(hits) == 1


def test_find_overlaps_ignores_adjacent_interval():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60))
    deps = _deps([existing])
    # new starts exactly when existing ends -> no overlap
    hits = _find_overlaps(deps, base + timedelta(minutes=60), base + timedelta(minutes=120))
    assert hits == []


def test_find_overlaps_excludes_self():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60))
    deps = _deps([existing])
    hits = _find_overlaps(deps, base, base + timedelta(minutes=60), exclude_event_id=existing.id)
    assert hits == []


@pytest.mark.asyncio
async def test_create_event_warns_on_conflict_but_still_succeeds():
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    existing = _ev(base, base + timedelta(minutes=60), client_name="Maria Silva")
    client = SimpleNamespace(id=uuid4(), name="Ana Souza", consult_price=200)
    deps = _deps([existing], client=client)
    deps.calendar_service.create_event.return_value = {"id": "g-1"}
    deps.event_service.record_event.return_value = SimpleNamespace(id=uuid4())
    out = await create_event_impl(deps, client_name="Ana", start_time=base + timedelta(minutes=30))
    assert out["success"] is True
    assert out["data"].get("conflict") is True
    assert "Atenção" in out["message"]
    assert "Maria" in out["message"]
