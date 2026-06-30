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


# ---- Finding 2: exclude_parent_id skips sibling occurrences ----

def test_find_overlaps_exclude_parent_id_skips_siblings():
    """Sibling occurrences (same parent_event_id) must not be flagged as conflicts."""
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    parent_id = uuid4()
    # A sibling occurrence sharing the same parent_event_id
    sibling = SimpleNamespace(
        id=uuid4(), parent_event_id=parent_id,
        start_time=base, end_time=base + timedelta(minutes=60),
        client=SimpleNamespace(name="Maria Silva"), client_id=uuid4(),
    )
    deps = _deps([sibling])
    hits = _find_overlaps(deps, base, base + timedelta(minutes=60), exclude_parent_id=parent_id)
    assert hits == [], "sibling occurrences must be excluded when exclude_parent_id is set"


def test_find_overlaps_exclude_parent_id_skips_template_itself():
    """An event whose id == exclude_parent_id must also be excluded (template itself)."""
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    parent_id = uuid4()
    template = SimpleNamespace(
        id=parent_id, parent_event_id=None,
        start_time=base, end_time=base + timedelta(minutes=60),
        client=SimpleNamespace(name="Maria Silva"), client_id=uuid4(),
    )
    deps = _deps([template])
    hits = _find_overlaps(deps, base, base + timedelta(minutes=60), exclude_parent_id=parent_id)
    assert hits == [], "template event itself must be excluded when its id == exclude_parent_id"


def test_find_overlaps_exclude_parent_id_keeps_unrelated_conflict():
    """An unrelated event must still be flagged even when exclude_parent_id is set."""
    base = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ))
    parent_id = uuid4()
    unrelated = SimpleNamespace(
        id=uuid4(), parent_event_id=uuid4(),  # different parent
        start_time=base, end_time=base + timedelta(minutes=60),
        client=SimpleNamespace(name="João Souza"), client_id=uuid4(),
    )
    deps = _deps([unrelated])
    hits = _find_overlaps(deps, base, base + timedelta(minutes=60), exclude_parent_id=parent_id)
    assert len(hits) == 1, "unrelated events must still appear as conflicts"
