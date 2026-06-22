from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.agents.tools.calendar_tools import set_session_charge_impl

TZ = ZoneInfo("America/Sao_Paulo")


def _deps(found, client):
    event_service = MagicMock()
    event_service.find_client_session_on_date.return_value = found

    def _set(ev, value):
        ev.billable = value
        return ev
    event_service.set_billable.side_effect = _set

    deps = SimpleNamespace(
        calendar_service=MagicMock(), event_service=event_service,
        user_id=uuid4(), timezone="America/Sao_Paulo",
        current_datetime=datetime(2026, 7, 7, 8, 0, tzinfo=TZ),
        client_service=MagicMock(),
    )
    # Mirror the real _resolve_client method signatures:
    # find_client_by_phone(phone, user_id) -> single client (or None)
    deps.client_service.find_client_by_phone = AsyncMock(return_value=client)
    # find_client_by_name(name, user_id) -> list of clients
    deps.client_service.find_client_by_name = AsyncMock(return_value=[client])
    return deps


async def test_sets_billable_true():
    client = SimpleNamespace(id=uuid4(), name="Maria Souza")
    ev = SimpleNamespace(id=uuid4(), billable=False)
    deps = _deps(ev, client)
    res = await set_session_charge_impl(deps, client_name="Maria", session_date="2026-07-07", charge=True)
    assert res["success"] is True
    assert ev.billable is True
    # message carries no id
    assert str(ev.id) not in res["message"]


async def test_unknown_session_is_reported():
    client = SimpleNamespace(id=uuid4(), name="Maria Souza")
    deps = _deps(None, client)
    res = await set_session_charge_impl(deps, client_name="Maria", session_date="2026-07-09", charge=False)
    assert res["success"] is False
