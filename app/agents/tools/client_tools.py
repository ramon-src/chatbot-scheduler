"""Client management tools: pure impls + thin @agent.tool wrappers."""

from decimal import Decimal
from typing import Optional

import pydantic

from app.agents.deps import AgentDeps
from app.core.exceptions import ConflictError, ValidationError
from app.schemas.client import ClientCreate, ClientUpdate


async def create_client_impl(
    deps: AgentDeps,
    name: str,
    phone: str,
    invoice_day: int,
    consult_price: float,
    email: Optional[str] = None,
    billing_mode: str = "monthly",
) -> dict:
    try:
        payload = ClientCreate(
            name=name, phone=phone, email=email, user_id=deps.user_id,
            invoice_day=invoice_day, consult_price=Decimal(str(consult_price)),
            billing_mode=billing_mode,
        )
    except pydantic.ValidationError:
        return {"success": False, "data": None,
                "message": "Não consegui validar os dados. Confira o telefone e o nome (nome e sobrenome)."}

    try:
        client = await deps.client_service.create_client(payload)
    except ConflictError as e:
        return {"success": False, "data": None, "message": str(e)}
    except ValidationError as e:
        return {"success": False, "data": None, "message": str(e)}

    first_name = client.name.split()[0]
    return {
        "success": True,
        "data": {"name": client.name, "phone": client.phone},
        "message": f"Cliente {first_name} cadastrado com sucesso.",
    }


async def find_client_impl(
    deps: AgentDeps,
    name: Optional[str] = None,
    phone: Optional[str] = None,
) -> dict:
    if phone:
        client = await deps.client_service.find_client_by_phone(phone, deps.user_id)
        if client:
            return {"success": True, "data": {"name": client.name, "phone": client.phone},
                    "message": f"Encontrei {client.name.split()[0]}."}
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente com o telefone {phone}."}

    if name:
        matches = await deps.client_service.find_client_by_name(name, deps.user_id)
        if len(matches) == 1:
            c = matches[0]
            return {"success": True, "data": {"name": c.name, "phone": c.phone},
                    "message": f"Encontrei {c.name.split()[0]}."}
        if len(matches) > 1:
            names = ", ".join(m.name for m in matches)
            return {"success": False, "data": {"candidates": names},
                    "message": f"Encontrei vários clientes para '{name}': {names}. "
                               f"Pode informar o telefone para identificar?"}
        first = name.split()[0]
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente chamado {first}. Quer cadastrar?"}

    return {"success": False, "data": None,
            "message": "Preciso do nome ou telefone do cliente para buscar."}


async def list_clients_impl(deps: AgentDeps, active_only: bool = True) -> dict:
    page = await deps.client_service.list_clients(
        deps.user_id, is_active=True if active_only else None, page=1, per_page=100
    )
    names = [c.name for c in page.clients]
    returned = len(names)
    truncated = page.total > returned
    if truncated:
        message = f"Você tem {page.total} clientes. Mostrando os primeiros {returned}."
    else:
        message = f"Você tem {page.total} cliente(s)."
    return {
        "success": True,
        "data": {"names": names, "total": page.total, "returned": returned, "truncated": truncated},
        "message": message,
    }


async def update_client_impl(deps: AgentDeps, phone: str, **fields) -> dict:
    client = await deps.client_service.find_client_by_phone(phone, deps.user_id)
    if not client:
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente com o telefone {phone}."}
    try:
        payload = ClientUpdate(**fields)
        updated = await deps.client_service.update_client(client.id, deps.user_id, payload)
    except (ConflictError, ValidationError) as e:
        return {"success": False, "data": None, "message": str(e)}
    except pydantic.ValidationError:
        return {"success": False, "data": None,
                "message": "Não consegui validar os dados. Confira o telefone e o nome (nome e sobrenome)."}
    return {"success": True, "data": {"name": updated.name, "phone": updated.phone},
            "message": f"Dados de {updated.name.split()[0]} atualizados."}


async def deactivate_client_impl(deps: AgentDeps, phone: str, reason: str) -> dict:
    client = await deps.client_service.find_client_by_phone(phone, deps.user_id)
    if not client:
        return {"success": False, "data": None,
                "message": f"Não encontrei cliente com o telefone {phone}."}
    await deps.client_service.deactivate_client(client.id, deps.user_id)
    return {"success": True, "data": {"name": client.name},
            "message": f"{client.name.split()[0]} foi desativado(a)."}


def register_client_tools(agent) -> None:
    """Register thin @agent.tool wrappers that delegate to the pure impls."""
    from pydantic_ai import RunContext

    @agent.tool
    async def create_client(
        ctx: RunContext[AgentDeps], name: str, phone: str,
        invoice_day: int, consult_price: float, email: Optional[str] = None,
        billing_mode: str = "monthly",
    ) -> dict:
        """Cadastra um cliente. billing_mode: 'monthly' (cobra por mês) ou 'per_session' (por consulta)."""
        return await create_client_impl(ctx.deps, name, phone, invoice_day, consult_price, email, billing_mode)

    @agent.tool
    async def find_client(
        ctx: RunContext[AgentDeps], name: Optional[str] = None, phone: Optional[str] = None,
    ) -> dict:
        """Busca um cliente por nome ou telefone."""
        return await find_client_impl(ctx.deps, name, phone)

    @agent.tool
    async def list_clients(ctx: RunContext[AgentDeps], active_only: bool = True) -> dict:
        """Lista os clientes do psicólogo."""
        return await list_clients_impl(ctx.deps, active_only)

    @agent.tool
    async def update_client(
        ctx: RunContext[AgentDeps],
        phone: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        invoice_day: Optional[int] = None,
        consult_price: Optional[float] = None,
        notes: Optional[str] = None,
        billing_mode: Optional[str] = None,
    ) -> dict:
        """Atualiza dados de um cliente identificado pelo telefone."""
        fields = {k: v for k, v in {
            "name": name, "email": email, "invoice_day": invoice_day,
            "consult_price": consult_price, "notes": notes, "billing_mode": billing_mode,
        }.items() if v is not None}
        return await update_client_impl(ctx.deps, phone, **fields)

    @agent.tool
    async def deactivate_client(ctx: RunContext[AgentDeps], phone: str, reason: str) -> dict:
        """Desativa um cliente (soft delete) com um motivo."""
        return await deactivate_client_impl(ctx.deps, phone, reason)
