"""mark_paid + list_pending_payments impls (mode-keyed)."""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.billing_tools import list_pending_payments_impl, mark_paid_impl

TZ = "America/Sao_Paulo"


def _client(mode="monthly", name="Maria Silva"):
    return SimpleNamespace(id=uuid4(), name=name, phone="+5551999990000",
                           consult_price=Decimal("200"), billing_mode=mode)


def _deps(client, *, pending=None, session=None):
    es = MagicMock()
    es.list_pending_payments.return_value = pending or []
    es.find_client_session_on_date.return_value = session
    es.set_payment_status.return_value = None
    cs = MagicMock()

    async def _by_phone(phone, user_id):
        return client

    async def _by_name(name, user_id):
        return [client] if client else []

    cs.find_client_by_phone = _by_phone
    cs.find_client_by_name = _by_name
    return SimpleNamespace(event_service=es, client_service=cs, user_id=uuid4(),
                           timezone=TZ, current_datetime=datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo(TZ)))


@pytest.mark.asyncio
async def test_mark_paid_per_session_by_date():
    client = _client(mode="per_session")
    sess = SimpleNamespace(id=uuid4(), price=Decimal("200"))
    deps = _deps(client, session=sess)
    out = await mark_paid_impl(deps, client_phone=client.phone, session_date="2026-06-24")
    assert out["success"] is True
    deps.event_service.set_payment_status.assert_called_once()


@pytest.mark.asyncio
async def test_mark_paid_per_session_without_date_asks():
    client = _client(mode="per_session")
    deps = _deps(client)
    out = await mark_paid_impl(deps, client_phone=client.phone)
    assert out["success"] is False
    assert "data" in out["message"].lower()


@pytest.mark.asyncio
async def test_mark_paid_monthly_marks_all_pending():
    client = _client(mode="monthly")
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200")),
            SimpleNamespace(id=uuid4(), price=Decimal("200"))]
    deps = _deps(client, pending=pend)
    out = await mark_paid_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert deps.event_service.set_payment_status.call_count == 2
    assert "400" in out["message"]


@pytest.mark.asyncio
async def test_list_pending_for_client_reports_total():
    client = _client()
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client),
            SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client)]
    deps = _deps(client, pending=pend)
    out = await list_pending_payments_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert "400" in out["message"]


@pytest.mark.asyncio
async def test_list_pending_empty():
    client = _client()
    deps = _deps(client, pending=[])
    out = await list_pending_payments_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert "pendente" in out["message"].lower() or "nenhum" in out["message"].lower()
