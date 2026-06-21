import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.agents.tools.client_tools import (
    create_client_impl,
    deactivate_client_impl,
    find_client_impl,
    list_clients_impl,
    update_client_impl,
)
from app.core.exceptions import ConflictError

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


@pytest.mark.asyncio
async def test_update_client_impl_not_found():
    service = MagicMock()
    service.find_client_by_phone = AsyncMock(return_value=None)
    deps = _deps_with_service(service)

    result = await update_client_impl(deps, phone="+5551981321543", name="Maria Silva")

    assert result["success"] is False
    assert "não encontrei" in result["message"].lower() or "não encontrei" in result["message"].casefold()
    service.find_client_by_phone.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivate_client_impl_success():
    service = MagicMock()
    client = SimpleNamespace(id=uuid4(), name="Ana Lima", phone="+5551981321543")
    service.find_client_by_phone = AsyncMock(return_value=client)
    service.deactivate_client = AsyncMock(return_value=None)
    deps = _deps_with_service(service)

    result = await deactivate_client_impl(deps, phone="+5551981321543", reason="Alta terapêutica")

    assert result["success"] is True
    assert "Ana" in result["message"]
    service.deactivate_client.assert_awaited_once_with(client.id, deps.user_id)


@pytest.mark.asyncio
async def test_create_client_impl_conflict_error():
    service = MagicMock()
    service.create_client = AsyncMock(
        side_effect=ConflictError("Já existe um cliente ativo com o telefone +5551981321543")
    )
    deps = _deps_with_service(service)

    result = await create_client_impl(
        deps, name="Maria Silva", phone="+5551981321543",
        invoice_day=10, consult_price=200.0,
    )

    assert result["success"] is False
    assert "Já existe um cliente ativo com o telefone +5551981321543" in result["message"]


@pytest.mark.asyncio
async def test_create_client_impl_validation_error_sanitized():
    service = MagicMock()
    service.create_client = AsyncMock()
    deps = _deps_with_service(service)

    # "X" fails ClientCreate validation (name requires ≥2 words / min length)
    result = await create_client_impl(
        deps, name="X", phone="+5551981321543",
        invoice_day=10, consult_price=200.0,
    )

    assert result["success"] is False
    assert result["message"].startswith("Não consegui validar os dados")
    assert "ValidationError" not in result["message"]
    assert "{" not in result["message"]
    service.create_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_clients_impl_returns_count():
    service = MagicMock()
    clients = [
        SimpleNamespace(name="Ana Lima"),
        SimpleNamespace(name="Carlos Souza"),
    ]
    page = SimpleNamespace(clients=clients, total=2)
    service.list_clients = AsyncMock(return_value=page)
    deps = _deps_with_service(service)

    result = await list_clients_impl(deps, active_only=True)

    assert result["success"] is True
    assert "2" in result["message"]
    service.list_clients.assert_awaited_once()
