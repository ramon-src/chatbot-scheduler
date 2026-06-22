# tests/unit/test_cancel_charge.py
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.agents.tools.calendar_tools import cancel_event_impl
from app.models.event import EventStatus

TZ = ZoneInfo("America/Sao_Paulo")


def _deps(events, client):
    calendar_service = MagicMock()
    event_service = MagicMock()
    event_service.list_events_in_range.return_value = events
    event_service.ensure_occurrences.return_value = 0

    def _cancel(ev, billable=None):
        ev.status = EventStatus.CANCELLED.value
        if billable is not None:
            ev.billable = billable
        return ev

    event_service.cancel_event.side_effect = _cancel

    client_service = MagicMock()
    # find_client_by_phone returns a single client (or None)
    client_service.find_client_by_phone = AsyncMock(return_value=None)
    # find_client_by_name returns a list of matches
    client_service.find_client_by_name = AsyncMock(return_value=[client])

    deps = SimpleNamespace(
        calendar_service=calendar_service,
        event_service=event_service,
        user_id=uuid4(),
        timezone="America/Sao_Paulo",
        current_datetime=datetime(2026, 7, 7, 8, 0, tzinfo=TZ),
        client_service=client_service,
    )
    return deps


def _event(client_id, start, *, google_id="g1", parent=None):
    return SimpleNamespace(
        id=uuid4(),
        client_id=client_id,
        start_time=start,
        google_event_id=google_id,
        parent_event_id=parent,
        billable=True,
        status=EventStatus.SCHEDULED.value,
    )


async def test_cancel_default_is_not_billable():
    client = SimpleNamespace(id=uuid4(), name="Joao Silva")
    ev = _event(client.id, datetime(2026, 7, 7, 9, 0, tzinfo=TZ))
    deps = _deps([ev], client)
    res = await cancel_event_impl(deps, client_name="Joao", period="today")
    assert res["success"] is True
    assert ev.billable is False  # cancellation defaults to not charged


async def test_cancel_with_charge_keeps_billable():
    client = SimpleNamespace(id=uuid4(), name="Joao Silva")
    ev = _event(client.id, datetime(2026, 7, 7, 9, 0, tzinfo=TZ))
    deps = _deps([ev], client)
    res = await cancel_event_impl(deps, client_name="Joao", period="today", charge=True)
    assert res["success"] is True
    assert ev.billable is True


async def test_cancel_occurrence_uses_best_effort_instance_cancel():
    client = SimpleNamespace(id=uuid4(), name="Joao Silva")
    parent = uuid4()
    ev = _event(client.id, datetime(2026, 7, 7, 9, 0, tzinfo=TZ), google_id=None, parent=parent)
    deps = _deps([ev], client)
    deps.event_service.get_event.return_value = SimpleNamespace(google_event_id="series-1")
    res = await cancel_event_impl(deps, client_name="Joao", period="today")
    assert res["success"] is True
    # occurrence (google_event_id is None, parent set) → cancel_occurrence path, not cancel_event
    deps.calendar_service.cancel_occurrence.assert_called_once()
    deps.calendar_service.cancel_event.assert_not_called()
