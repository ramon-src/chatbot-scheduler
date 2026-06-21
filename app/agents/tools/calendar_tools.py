"""Agenda tools: pure impls + thin @agent.tool wrappers. Google Calendar is source of truth."""

from datetime import datetime, timedelta
from typing import Optional

from app.agents.deps import AgentDeps
from app.utils.date_range import calculate_date_range

def _not_connected() -> dict:
    """Fresh graceful-degradation dict (avoid sharing a mutable module constant)."""
    return {
        "success": False, "data": None,
        "message": "Você ainda não conectou sua Google Agenda. Posso te ajudar a conectar quando quiser.",
    }


def _fmt(dt: datetime) -> str:
    return dt.strftime("%d/%m às %Hh%M").replace("h00", "h")


async def _resolve_client(deps: AgentDeps, client_name, client_phone):
    """Return (client, error_dict). Exactly one of client/error is non-None."""
    if client_phone:
        client = await deps.client_service.find_client_by_phone(client_phone, deps.user_id)
        if client:
            return client, None
        return None, {"success": False, "data": None,
                      "message": f"Não encontrei cliente com o telefone {client_phone}. Quer cadastrar primeiro?"}
    if client_name:
        matches = await deps.client_service.find_client_by_name(client_name, deps.user_id)
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            names = ", ".join(m.name for m in matches)
            return None, {"success": False, "data": {"candidates": names},
                          "message": f"Encontrei vários clientes para '{client_name}': {names}. "
                                     f"Pode informar o telefone?"}
        first = client_name.split()[0]
        return None, {"success": False, "data": None,
                      "message": f"Não encontrei cliente chamado {first}. Quer cadastrar primeiro?"}
    return None, {"success": False, "data": None,
                  "message": "Preciso do nome ou telefone do cliente para agendar."}


async def create_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    start_time: datetime, duration_minutes: Optional[int] = None, title: Optional[str] = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error

    minutes = duration_minutes or deps.default_consult_minutes
    end = start_time + timedelta(minutes=minutes)
    summary = title or f"Sessão - {client.name}"

    created = deps.calendar_service.create_event(summary=summary, start=start_time, end=end)
    deps.event_service.record_event(
        user_id=deps.user_id, client_id=client.id, title=summary,
        start=start_time, end=end, google_event_id=created["id"],
    )
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name, "start": start_time.isoformat()},
            "message": f"Agendei {first} para {_fmt(start_time)}."}


async def create_recurring_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None, start_time: datetime,
    frequency: str = "weekly", weekdays=None, until=None,
    duration_minutes: Optional[int] = None, title: Optional[str] = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error

    minutes = duration_minutes or deps.default_consult_minutes
    end = start_time + timedelta(minutes=minutes)
    summary = title or f"Sessão - {client.name}"
    rrule = deps.calendar_service.build_weekly_rrule(weekdays, until)

    created = deps.calendar_service.create_event(
        summary=summary, start=start_time, end=end, recurrence=[rrule]
    )
    deps.event_service.record_event(
        user_id=deps.user_id, client_id=client.id, title=summary,
        start=start_time, end=end, google_event_id=created["id"],
        is_recurring=True, recurrence_rule=rrule,
    )
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Agendei sessões recorrentes para {first}, começando {_fmt(start_time)}."}


async def list_events_impl(deps: AgentDeps, period: str = "this_week") -> dict:
    if deps.event_service is None:
        return _not_connected()
    try:
        start, end = calculate_date_range(period, deps.current_datetime)
    except ValueError:
        return {"success": False, "data": None,
                "message": "Não entendi o período. Tente 'hoje', 'esta semana' ou 'este mês'."}

    events = deps.event_service.list_events_in_range(deps.user_id, start, end)
    items = [{"title": e.title, "start": e.start_time.isoformat()} for e in events]
    if not items:
        return {"success": True, "data": {"events": [], "total": 0},
                "message": "Você não tem compromissos nesse período."}
    lines = "; ".join(f"{e.title} em {_fmt(e.start_time)}" for e in events)
    return {"success": True, "data": {"events": items, "total": len(items)},
            "message": f"Você tem {len(items)} compromisso(s): {lines}."}


async def cancel_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    period: str = "this_week", reason: Optional[str] = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    try:
        start, end = calculate_date_range(period, deps.current_datetime)
    except ValueError:
        return {"success": False, "data": None,
                "message": "Não entendi o período. Tente 'hoje' ou 'esta semana'."}

    events = [
        e for e in deps.event_service.list_events_in_range(deps.user_id, start, end)
        if e.client_id == client.id
    ]
    if not events:
        first = client.name.split()[0]
        return {"success": False, "data": None,
                "message": f"Não encontrei compromisso de {first} nesse período."}
    if len(events) > 1:
        return {"success": False, "data": {"count": len(events)},
                "message": "Encontrei mais de um compromisso nesse período. Pode me dizer o dia exato?"}

    event = events[0]
    deps.calendar_service.cancel_event(event.google_event_id)
    deps.event_service.cancel_event(event)
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Cancelei o compromisso de {first}."}


def register_calendar_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def create_event(
        ctx: RunContext[AgentDeps], start_time: str,
        client_name: Optional[str] = None, client_phone: Optional[str] = None,
        duration_minutes: Optional[int] = None, title: Optional[str] = None,
    ) -> dict:
        """Agenda um compromisso único. start_time em ISO 8601. Exige cliente já cadastrado."""
        return await create_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            start_time=datetime.fromisoformat(start_time),
            duration_minutes=duration_minutes, title=title,
        )

    @agent.tool
    async def create_recurring_event(
        ctx: RunContext[AgentDeps], start_time: str,
        client_name: Optional[str] = None, client_phone: Optional[str] = None,
        weekdays: Optional[list[str]] = None, until: Optional[str] = None,
        duration_minutes: Optional[int] = None, title: Optional[str] = None,
    ) -> dict:
        """Agenda sessões recorrentes semanais. start_time/until em ISO 8601. weekdays como ['TU','TH']."""
        return await create_recurring_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            start_time=datetime.fromisoformat(start_time),
            weekdays=weekdays, until=datetime.fromisoformat(until) if until else None,
            duration_minutes=duration_minutes, title=title,
        )

    @agent.tool
    async def list_events(ctx: RunContext[AgentDeps], period: str = "this_week") -> dict:
        """Lista compromissos da agenda em um período (today, tomorrow, this_week, next_week, this_month)."""
        return await list_events_impl(ctx.deps, period)

    @agent.tool
    async def cancel_event(
        ctx: RunContext[AgentDeps], client_name: Optional[str] = None,
        client_phone: Optional[str] = None, period: str = "this_week", reason: Optional[str] = None,
    ) -> dict:
        """Cancela o compromisso de um cliente num período. Exige cliente cadastrado."""
        return await cancel_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone, period=period, reason=reason
        )
