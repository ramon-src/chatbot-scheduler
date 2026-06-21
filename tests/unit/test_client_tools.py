import pytest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.agents.tools.client_tools import (
    create_client_impl,
    find_client_impl,
)

def _deps_with_service(service):
    return SimpleNamespace(
        db=MagicMock(), user_id=uuid4(), user_name="Ramon",
        current_datetime=None, timezone="America/Sao_Paulo",
        history_summary=None, client_service=service,
    )

@pytest.mark.asyncio
async def test_create_client_impl_success():
    service = MagicMock()
    created = SimpleNamespace(name="Maria Silva", phone="+5551981321543")
    service.create_client = AsyncMock(return_value=created)
    deps = _deps_with_service(service)

    result = await create_client_impl(
        deps, name="Maria Silva", phone="+5551981321543",
        invoice_day=10, consult_price=200.0,
    )

    assert result["success"] is True
    assert "Maria" in result["message"]
    service.create_client.assert_awaited_once()

@pytest.mark.asyncio
async def test_find_client_impl_not_found_returns_actionable_message():
    service = MagicMock()
    service.find_client_by_phone = AsyncMock(return_value=None)
    service.find_client_by_name = AsyncMock(return_value=[])
    deps = _deps_with_service(service)

    result = await find_client_impl(deps, name="Carlos Souza")

    assert result["success"] is False
    assert "Carlos" in result["message"]
