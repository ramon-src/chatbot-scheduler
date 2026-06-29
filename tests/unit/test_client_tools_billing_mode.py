"""create_client_impl / update_client_impl thread billing_mode to the service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.tools.client_tools import create_client_impl, update_client_impl


def _deps():
    svc = SimpleNamespace(create_client=AsyncMock(return_value=SimpleNamespace(name="Maria Silva", phone="+5551999990000")),
                          update_client=AsyncMock(return_value=SimpleNamespace(name="Maria Silva", phone="+5551999990000")),
                          find_client_by_phone=AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="Maria Silva")))
    return SimpleNamespace(client_service=svc, user_id=uuid4())


@pytest.mark.asyncio
async def test_create_passes_billing_mode():
    deps = _deps()
    await create_client_impl(deps, "Maria Silva", "+5551999990000", 10, 200, billing_mode="per_session")
    payload = deps.client_service.create_client.call_args.args[0]
    assert payload.billing_mode == "per_session"


@pytest.mark.asyncio
async def test_update_passes_billing_mode():
    deps = _deps()
    await update_client_impl(deps, "+5551999990000", billing_mode="monthly")
    payload = deps.client_service.update_client.call_args.args[2]
    assert payload.billing_mode == "monthly"
