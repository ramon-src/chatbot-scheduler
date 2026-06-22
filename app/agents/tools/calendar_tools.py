"""Agenda tools: pure impls + thin @agent.tool wrappers. Google Calendar is source of truth."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.agents.deps import AgentDeps
from app.utils.date_range import calculate_date_range


def _not_connected() -> dict:
    """Fresh graceful-degradation dict (avoid sharing a mutable module constant)."""
    return {
        "success": False, "data": None,
        "message": "Você ainda não conectou sua Google Agenda. Posso te ajudar a conectar quando quiser.",
    }


def _dual_write_failed() -> dict:
    return {"success": False, "data": None,
            "message": "Tive um problema ao registrar o agendamento. Pode tentar de novo?"}


def _compensate_google(deps: AgentDeps, google_event_id: str) -> None:
    """Best-effort rollback of a Google event whose local mirror write failed."""
    try:
        deps.calendar_service.cancel_event(google_event_id)
    except Exception:
        pass  # nothing more we can do; surfaced to the user as a retry prompt


def _ensure_aware(dt: datetime, tz: str) -> datetime:
    """A naive datetime is assumed to already be in the professional's timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def _fmt(dt: datetime, tz: str) -> str:
    """Format in the professional's timezone (DB stores UTC-aware datetimes)."""
    local = _ensure_aware(dt, tz).astimezone(ZoneInfo(tz))
    return local.strftime("%d/%m às %Hh%M").replace("h00", "h")


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
    start_time: datetime, duration_minutes: int | None = None, title: str | None = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error

    start_time = _ensure_aware(start_time, deps.timezone)
    minutes = duration_minutes or deps.default_consult_minutes
    end = start_time + timedelta(minutes=minutes)
    summary = title or f"Sessão - {client.name}"

    created = deps.calendar_service.create_event(summary=summary, start=start_time, end=end)
    try:
        deps.event_service.record_event(
            user_id=deps.user_id, client_id=client.id, title=summary,
            start=start_time, end=end, google_event_id=created["id"],
        )
    except Exception:
        # Local write failed after the Google event was created: compensate by
        # removing the orphan so the two stores stay consistent, then degrade.
        _compensate_google(deps, created["id"])
        return _dual_write_failed()
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name, "start": start_time.isoformat()},
            "message": f"Agendei {first} para {_fmt(start_time, deps.timezone)}."}


async def create_recurring_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None, start_time: datetime,
    frequency: str = "weekly", weekdays=None, until=None,
    duration_minutes: int | None = None, title: str | None = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error

    start_time = _ensure_aware(start_time, deps.timezone)
    minutes = duration_minutes or deps.default_consult_minutes
    end = start_time + timedelta(minutes=minutes)
    summary = title or f"Sessão - {client.name}"
    rrule = deps.calendar_service.build_weekly_rrule(weekdays, until)

    created = deps.calendar_service.create_event(
        summary=summary, start=start_time, end=end, recurrence=[rrule]
    )
    try:
        deps.event_service.record_event(
            user_id=deps.user_id, client_id=client.id, title=summary,
            start=start_time, end=end, google_event_id=created["id"],
            is_recurring=True, recurrence_rule=rrule,
        )
    except Exception:
        _compensate_google(deps, created["id"])
        return _dual_write_failed()
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Agendei sessões recorrentes para {first}, começando {_fmt(start_time, deps.timezone)}."}


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
    lines = "; ".join(f"{e.title} em {_fmt(e.start_time, deps.timezone)}" for e in events)
    return {"success": True, "data": {"events": items, "total": len(items)},
            "message": f"Você tem {len(items)} compromisso(s): {lines}."}


async def cancel_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    period: str = "this_week", reason: str | None = None,
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
    # Google is the source of truth: cancel there first. If the local mirror
    # update then fails, the authoritative cancellation already succeeded — keep
    # the success response rather than confusing the user with a false failure.
    deps.calendar_service.cancel_event(event.google_event_id)
    try:
        deps.event_service.cancel_event(event)
    except Exception:
        pass
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Cancelei o compromisso de {first}."}


def register_calendar_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def create_event(
        ctx: RunContext[AgentDeps], start_time: str,
        client_name: str | None = None, client_phone: str | None = None,
        duration_minutes: int | None = None, title: str | None = None,
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
        client_name: str | None = None, client_phone: str | None = None,
        weekdays: list[str] | None = None, until: str | None = None,
        duration_minutes: int | None = None, title: str | None = None,
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
        ctx: RunContext[AgentDeps], client_name: str | None = None,
        client_phone: str | None = None, period: str = "this_week", reason: str | None = None,
    ) -> dict:
        """Cancela o compromisso de um cliente num período. Exige cliente cadastrado."""
        return await cancel_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone, period=period, reason=reason
        )
