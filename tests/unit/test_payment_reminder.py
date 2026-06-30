"""send_payment_reminder_impl sends a client-scoped reminder via outbound."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.agents.tools.billing_tools import send_payment_reminder_impl

TZ = "America/Sao_Paulo"


class _FakeOutbound:
    provider = "fake"

    def __init__(self):
        self.sent = []

    def send(self, message) -> bool:
        self.sent.append(message)
        return True


def _client(mode="monthly"):
    return SimpleNamespace(id=uuid4(), name="Maria Silva", phone="+5551999990000",
                           consult_price=Decimal("200"), billing_mode=mode)


def _deps(client, *, pending, outbound):
    es = MagicMock()
    es.list_pending_payments.return_value = pending
    cs = MagicMock()

    async def _by_phone(phone, user_id):
        return client

    cs.find_client_by_phone = _by_phone
    return SimpleNamespace(event_service=es, client_service=cs, outbound=outbound, user_id=uuid4(),
                           timezone=TZ, current_datetime=datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo(TZ)))


@pytest.mark.asyncio
async def test_reminder_sent_to_client_with_amount():
    client = _client()
    ob = _FakeOutbound()
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client),
            SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client)]
    deps = _deps(client, pending=pend, outbound=ob)
    out = await send_payment_reminder_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert len(ob.sent) == 1
    assert ob.sent[0].to_phone == client.phone
    assert "400" in ob.sent[0].text
    assert "Maria" in ob.sent[0].text


@pytest.mark.asyncio
async def test_reminder_nothing_pending_sends_nothing():
    client = _client()
    ob = _FakeOutbound()
    deps = _deps(client, pending=[], outbound=ob)
    out = await send_payment_reminder_impl(deps, client_phone=client.phone)
    assert out["success"] is True
    assert ob.sent == []
    assert "em aberto" in out["message"].lower() or "pendente" in out["message"].lower()


@pytest.mark.asyncio
async def test_reminder_no_outbound_degrades():
    client = _client()
    pend = [SimpleNamespace(id=uuid4(), price=Decimal("200"), client=client)]
    deps = _deps(client, pending=pend, outbound=None)
    out = await send_payment_reminder_impl(deps, client_phone=client.phone)
    assert out["success"] is False
