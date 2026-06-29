"""Billing tools: pure impls + thin @agent.tool wrappers. Tracking on Event.payment_status."""

from datetime import date as _date
from datetime import datetime
from decimal import Decimal

from app.agents.deps import AgentDeps
from app.agents.tools.calendar_tools import _resolve_client
from app.channels.outbound import OutboundMessage
from app.models.event import PaymentStatus
from app.utils.date_range import calculate_date_range


def _unavailable() -> dict:
    return {"success": False, "data": None,
            "message": "Não consigo acessar a cobrança agora. Tente de novo em instantes."}


def _brl(value) -> str:
    return f"R$ {Decimal(str(value or 0)):.2f}"


def _month_window(when: datetime):
    start = when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start.replace(year=start.year + 1, month=1) if start.month == 12
           else start.replace(month=start.month + 1))
    return start, nxt


def _total(events) -> Decimal:
    return sum((Decimal(str(e.price or 0)) for e in events), Decimal("0"))


async def mark_paid_impl(deps: AgentDeps, *, client_name=None, client_phone=None,
                         session_date=None, month=None) -> dict:
    if deps.event_service is None:
        return _unavailable()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    mode = getattr(client, "billing_mode", "monthly")
    first = client.name.split()[0]

    if mode == "per_session":
        if not session_date:
            return {"success": False, "data": None,
                    "message": f"Qual a data da consulta de {first} que foi paga? (dia/mês)"}
        try:
            day = _date.fromisoformat(session_date)
        except ValueError:
            return {"success": False, "data": None,
                    "message": "Não entendi a data. Use o formato AAAA-MM-DD."}
        event = deps.event_service.find_client_session_on_date(deps.user_id, client.id, day)
        if event is None:
            return {"success": False, "data": None,
                    "message": f"Não encontrei consulta de {first} nessa data."}
        deps.event_service.set_payment_status(event, PaymentStatus.PAID.value)
        return {"success": True, "data": {"client": client.name},
                "message": f"Marquei a consulta de {first} como paga."}

    # monthly
    if month is None:
        ref = deps.current_datetime
    else:
        raw = month.strip()
        if len(raw) == 7:  # YYYY-MM — append day so fromisoformat accepts it
            raw = raw + "-01"
        try:
            ref = datetime.fromisoformat(raw)
        except ValueError:
            return {"success": False, "data": None,
                    "message": "Não entendi o mês. Tente algo como 'junho' ou 2026-06."}
    start, end = _month_window(ref)
    pending = deps.event_service.list_pending_payments(
        deps.user_id, client_id=client.id, start=start, end=end, now=deps.current_datetime)
    if not pending:
        return {"success": True, "data": {"client": client.name, "count": 0},
                "message": f"{first} não tem consultas em aberto nesse mês."}
    for e in pending:
        deps.event_service.set_payment_status(e, PaymentStatus.PAID.value)
    total = _total(pending)
    return {"success": True, "data": {"client": client.name, "count": len(pending)},
            "message": f"Marquei o mês de {first} como pago: {len(pending)} consulta(s), {_brl(total)}."}


async def list_pending_payments_impl(deps: AgentDeps, *, client_name=None,
                                     client_phone=None, period=None) -> dict:
    if deps.event_service is None:
        return _unavailable()
    start = end = None
    if period:
        try:
            start, end = calculate_date_range(period, deps.current_datetime)
        except ValueError:
            return {"success": False, "data": None,
                    "message": "Não entendi o período. Tente 'este mês' ou 'esta semana'."}

    if client_name or client_phone:
        client, error = await _resolve_client(deps, client_name, client_phone)
        if error:
            return error
        pending = deps.event_service.list_pending_payments(
            deps.user_id, client_id=client.id, start=start, end=end, now=deps.current_datetime)
        first = client.name.split()[0]
        if not pending:
            return {"success": True, "data": {"client": client.name, "count": 0},
                    "message": f"{first} não tem pagamentos pendentes."}
        return {"success": True, "data": {"client": client.name, "count": len(pending)},
                "message": f"{first} tem {len(pending)} consulta(s) em aberto, total {_brl(_total(pending))}."}

    pending = deps.event_service.list_pending_payments(
        deps.user_id, start=start, end=end, now=deps.current_datetime)
    if not pending:
        return {"success": True, "data": {"count": 0},
                "message": "Você não tem pagamentos pendentes."}
    by_client: dict = {}
    for e in pending:
        name = e.client.name if getattr(e, "client", None) else "cliente"
        slot = by_client.setdefault(name, [Decimal("0"), 0])
        slot[0] += Decimal(str(e.price or 0))
        slot[1] += 1
    parts = "; ".join(f"{n.split()[0]}: {c} consulta(s), {_brl(v)}" for n, (v, c) in by_client.items())
    return {"success": True, "data": {"count": len(pending)},
            "message": f"Pagamentos em aberto — {parts}. Total {_brl(_total(pending))}."}


async def send_payment_reminder_impl(deps: AgentDeps, *, client_name=None,
                                     client_phone=None, period=None) -> dict:
    if deps.event_service is None:
        return _unavailable()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    first = client.name.split()[0]
    if not getattr(client, "phone", None):
        return {"success": False, "data": None,
                "message": f"Não tenho o telefone de {first} para enviar o lembrete."}
    if deps.outbound is None:
        return {"success": False, "data": None,
                "message": "O envio de mensagens não está disponível agora. Tente mais tarde."}

    start = end = None
    if period:
        try:
            start, end = calculate_date_range(period, deps.current_datetime)
        except ValueError:
            return {"success": False, "data": None,
                    "message": "Não entendi o período. Tente 'este mês'."}
    pending = deps.event_service.list_pending_payments(
        deps.user_id, client_id=client.id, start=start, end=end, now=deps.current_datetime)
    if not pending:
        return {"success": True, "data": {"client": client.name, "count": 0},
                "message": f"{first} não tem pagamentos em aberto."}

    total = _total(pending)
    mode = getattr(client, "billing_mode", "monthly")
    if mode == "per_session" and len(pending) == 1:
        when = pending[0].start_time.astimezone(__import__("zoneinfo").ZoneInfo(deps.timezone)).strftime("%d/%m")
        text = (f"Olá {first}! Passando pra lembrar do pagamento da sua consulta de {when}, "
                f"no valor de {_brl(total)}. Qualquer coisa, estou à disposição.")
    else:
        text = (f"Olá {first}! Passando pra lembrar do pagamento de {len(pending)} consulta(s), "
                f"no total de {_brl(total)}. Qualquer coisa, estou à disposição.")
    ok = deps.outbound.send(OutboundMessage(to_phone=client.phone, text=text))
    if not ok:
        return {"success": False, "data": None,
                "message": f"Não consegui enviar o lembrete para {first} agora. Tente de novo."}
    return {"success": True, "data": {"client": client.name, "count": len(pending)},
            "message": f"Enviei o lembrete de pagamento para {first}."}


def register_billing_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def mark_paid(
        ctx: RunContext[AgentDeps], client_name: str | None = None,
        client_phone: str | None = None, session_date: str | None = None,
        month: str | None = None,
    ) -> dict:
        """Marca consulta(s) como pagas. Cliente per_session: informe session_date (AAAA-MM-DD).
        Cliente mensal: usa o mês (month ISO opcional, padrão o mês atual)."""
        return await mark_paid_impl(ctx.deps, client_name=client_name, client_phone=client_phone,
                                    session_date=session_date, month=month)

    @agent.tool
    async def list_pending_payments(
        ctx: RunContext[AgentDeps], client_name: str | None = None,
        client_phone: str | None = None, period: str | None = None,
    ) -> dict:
        """Lista pagamentos em aberto (de um cliente ou de todos), com totais."""
        return await list_pending_payments_impl(ctx.deps, client_name=client_name,
                                                client_phone=client_phone, period=period)

    @agent.tool
    async def send_payment_reminder(
        ctx: RunContext[AgentDeps], client_name: str | None = None,
        client_phone: str | None = None, period: str | None = None,
    ) -> dict:
        """Envia um lembrete de pagamento ao WhatsApp do próprio cliente, com o total em aberto."""
        return await send_payment_reminder_impl(ctx.deps, client_name=client_name,
                                                client_phone=client_phone, period=period)
