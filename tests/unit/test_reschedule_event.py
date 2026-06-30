"""reschedule_event_impl: single-event move + conflict warning + errors."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.calendar_tools import reschedule_event_impl

TZ = "America/Sao_Paulo"


def _deps(found_event, *, client, overlaps=None, template=None):
    es = MagicMock()
    es.ensure_occurrences.return_value = 0
    # _find_single_event_for_client uses list_events_in_range filtered by client_id;
    # _find_overlaps uses it too. Return the client's event for the finder and the
    # overlaps for the conflict scan via side_effect ordering.
    es.list_events_in_range.side_effect = [[found_event], overlaps or []]
    es.update_event.return_value = found_event
    if template is not None:
        es.get_event.return_value = template
    cs = MagicMock()

    async def _by_name(name, user_id):
        return [client]

    async def _by_phone(phone, user_id):
        return client

    cs.find_client_by_name = _by_name
    cs.find_client_by_phone = _by_phone
    return SimpleNamespace(
        event_service=es, client_service=cs, calendar_service=MagicMock(),
        user_id=uuid4(), timezone=TZ, default_consult_minutes=60,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )


@pytest.mark.asyncio
async def test_reschedule_single_updates_both_stores():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    ev = SimpleNamespace(id=uuid4(), client_id=cid, parent_event_id=None,
                         is_recurring=False, google_event_id="g-1")
    deps = _deps(ev, client=client)
    new_start = datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ))
    out = await reschedule_event_impl(deps, client_name="Maria", new_start_time=new_start)
    assert out["success"] is True
    assert "Remarquei" in out["message"]
    deps.calendar_service.update_event.assert_called_once()
    deps.event_service.update_event.assert_called_once()


@pytest.mark.asyncio
async def test_reschedule_warns_on_conflict():
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    ev = SimpleNamespace(id=uuid4(), client_id=cid, parent_event_id=None,
                         is_recurring=False, google_event_id="g-1")
    overlap = SimpleNamespace(id=uuid4(), client=SimpleNamespace(name="João Souza"),
                              start_time=datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ)),
                              end_time=datetime(2026, 6, 24, 16, 0, tzinfo=ZoneInfo(TZ)))
    deps = _deps(ev, client=client, overlaps=[overlap])
    new_start = datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ))
    out = await reschedule_event_impl(deps, client_name="Maria", new_start_time=new_start)
    assert out["success"] is True
    assert "Atenção" in out["message"] and "João" in out["message"]


@pytest.mark.asyncio
async def test_reschedule_unknown_client_errors():
    cs = MagicMock()

    async def _none_name(name, user_id):
        return []

    cs.find_client_by_name = _none_name
    deps = SimpleNamespace(
        event_service=MagicMock(), client_service=cs, calendar_service=MagicMock(),
        user_id=uuid4(), timezone=TZ, default_consult_minutes=60,
        current_datetime=datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo(TZ)),
    )
    out = await reschedule_event_impl(deps, client_name="Fulano",
                                      new_start_time=datetime(2026, 6, 24, 15, 0, tzinfo=ZoneInfo(TZ)))
    assert out["success"] is False


# ---- Finding 1: weekday-change guard on series reschedule ----

@pytest.mark.asyncio
async def test_reschedule_series_different_weekday_returns_refusal():
    """Rescheduling a recurring occurrence to a different weekday must be refused."""
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    template_id = uuid4()
    template = SimpleNamespace(
        id=template_id, client_id=cid, parent_event_id=None,
        is_recurring=True, google_event_id="g-template",
        start_time=datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ)),  # Tuesday
    )
    # Occurrence on Tuesday (weekday 1)
    ev = SimpleNamespace(
        id=uuid4(), client_id=cid, parent_event_id=template_id,
        is_recurring=False, google_event_id="g-occ",
        start_time=datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ)),  # Tuesday
    )
    deps = _deps(ev, client=client, template=template)
    # Attempt to move to Wednesday (weekday 2) — different weekday
    new_start = datetime(2026, 6, 24, 10, 0, tzinfo=ZoneInfo(TZ))  # Wednesday
    assert ev.start_time.weekday() != new_start.weekday(), "Test setup: must be different weekdays"
    out = await reschedule_event_impl(deps, client_name="Maria", new_start_time=new_start)
    assert out["success"] is False
    assert "dia da semana" in out["message"]
    # Must NOT mutate Google or mirror
    deps.calendar_service.update_event.assert_not_called()
    deps.event_service.reschedule_series.assert_not_called()


@pytest.mark.asyncio
async def test_reschedule_series_same_weekday_different_hour_succeeds():
    """Rescheduling a recurring occurrence to the same weekday (different time) must succeed."""
    cid = uuid4()
    client = SimpleNamespace(id=cid, name="Maria Silva")
    template_id = uuid4()
    template = SimpleNamespace(
        id=template_id, client_id=cid, parent_event_id=None,
        is_recurring=True, google_event_id="g-template",
        start_time=datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ)),  # Tuesday 10h
    )
    # Occurrence on Tuesday (weekday 1) at 10h
    ev = SimpleNamespace(
        id=uuid4(), client_id=cid, parent_event_id=template_id,
        is_recurring=False, google_event_id="g-occ",
        start_time=datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo(TZ)),  # Tuesday
    )
    deps = _deps(ev, client=client, template=template)
    # Move to Tuesday 15h — same weekday, different hour
    new_start = datetime(2026, 6, 23, 15, 0, tzinfo=ZoneInfo(TZ))  # same Tuesday
    assert ev.start_time.weekday() == new_start.weekday(), "Test setup: must be same weekday"
    out = await reschedule_event_impl(deps, client_name="Maria", new_start_time=new_start)
    assert out["success"] is True
    assert "Remarquei" in out["message"]
    deps.calendar_service.update_event.assert_called_once()
    deps.event_service.reschedule_series.assert_called_once()
