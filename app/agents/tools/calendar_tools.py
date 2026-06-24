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


def _day_bounds(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Full-day window spanning [start, end), so list_events_in_range (which filters
    by start_time) catches same-day events regardless of time."""
    from datetime import time
    lo = datetime.combine(start.date(), time.min, tzinfo=start.tzinfo)
    hi = datetime.combine(end.date(), time.max, tzinfo=end.tzinfo)
    return lo, hi


def _find_overlaps(deps: AgentDeps, start: datetime, end: datetime, *, exclude_event_id=None) -> list:
    """Active events of the professional whose [start_time, end_time) overlaps [start, end).
    list_events_in_range already excludes cancelled events and series templates."""
    if deps.event_service is None:
        return []
    lo, hi = _day_bounds(start, end)
    deps.event_service.ensure_occurrences(deps.user_id, lo, hi)
    hits = []
    for e in deps.event_service.list_events_in_range(deps.user_id, lo, hi):
        if exclude_event_id is not None and e.id == exclude_event_id:
            continue
        if e.start_time < end and start < e.end_time:
            hits.append(e)
    return hits


def _conflict_warning(deps: AgentDeps, conflicts: list) -> tuple[str, str | None]:
    """Plain-text warning suffix + the conflicting client's first name (or None)."""
    if not conflicts:
        return "", None
    other = conflicts[0]
    name = other.client.name.split()[0] if getattr(other, "client", None) else "outro cliente"
    return f" Atenção: você já tem {name} nesse horário.", name


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

    conflicts = _find_overlaps(deps, start_time, end)

    created = deps.calendar_service.create_event(summary=summary, start=start_time, end=end)
    try:
        deps.event_service.record_event(
            user_id=deps.user_id, client_id=client.id, title=summary,
            start=start_time, end=end, google_event_id=created["id"],
            price=client.consult_price,
        )
    except Exception:
        # Local write failed after the Google event was created: compensate by
        # removing the orphan so the two stores stay consistent, then degrade.
        _compensate_google(deps, created["id"])
        return _dual_write_failed()
    first = client.name.split()[0]
    warning, who = _conflict_warning(deps, conflicts)
    data = {"client": client.name, "start": start_time.isoformat()}
    if who:
        data["conflict"] = True
        data["conflict_with"] = who
    return {"success": True, "data": data,
            "message": f"Agendei {first} para {_fmt(start_time, deps.timezone)}." + warning}


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

    conflicts = _find_overlaps(deps, start_time, end)

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
    warning, who = _conflict_warning(deps, conflicts)
    data = {"client": client.name}
    if who:
        data["conflict"] = True
        data["conflict_with"] = who
    return {"success": True, "data": data,
            "message": f"Agendei sessões recorrentes para {first}, começando {_fmt(start_time, deps.timezone)}." + warning}


async def list_events_impl(deps: AgentDeps, period: str = "this_week") -> dict:
    if deps.event_service is None:
        return _not_connected()
    try:
        start, end = calculate_date_range(period, deps.current_datetime)
    except ValueError:
        return {"success": False, "data": None,
                "message": "Não entendi o período. Tente 'hoje', 'esta semana' ou 'este mês'."}

    deps.event_service.ensure_occurrences(deps.user_id, start, end)
    events = deps.event_service.list_events_in_range(deps.user_id, start, end)
    items = [{"title": e.title, "start": e.start_time.isoformat()} for e in events]
    if not items:
        return {"success": True, "data": {"events": [], "total": 0},
                "message": "Você não tem compromissos nesse período."}
    lines = "; ".join(f"{e.title} em {_fmt(e.start_time, deps.timezone)}" for e in events)
    return {"success": True, "data": {"events": items, "total": len(items)},
            "message": f"Você tem {len(items)} compromisso(s): {lines}."}


def _find_single_event_for_client(deps, client, period: str):
    """Return (event, error). Exactly one is non-None. Mirrors cancel's resolution:
    0 matches -> not-found; >1 -> ask for the exact day."""
    try:
        start, end = calculate_date_range(period, deps.current_datetime)
    except ValueError:
        return None, {"success": False, "data": None,
                      "message": "Não entendi o período. Tente 'hoje' ou 'esta semana'."}
    deps.event_service.ensure_occurrences(deps.user_id, start, end)
    events = [
        e for e in deps.event_service.list_events_in_range(deps.user_id, start, end)
        if e.client_id == client.id
    ]
    if not events:
        first = client.name.split()[0]
        return None, {"success": False, "data": None,
                      "message": f"Não encontrei compromisso de {first} nesse período."}
    if len(events) > 1:
        return None, {"success": False, "data": {"count": len(events)},
                      "message": "Encontrei mais de um compromisso nesse período. Pode me dizer o dia exato?"}
    return events[0], None


async def cancel_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    period: str = "this_week", reason: str | None = None,
    charge: bool | None = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error

    event, error = _find_single_event_for_client(deps, client, period)
    if error:
        return error
    billable = charge if charge is not None else False
    # Google is the source of truth: cancel there first (best-effort).
    try:
        if event.parent_event_id is not None:
            parent = deps.event_service.get_event(event.parent_event_id)
            if parent is not None and parent.google_event_id:
                deps.calendar_service.cancel_occurrence(parent.google_event_id, event.start_time)
        elif event.google_event_id:
            deps.calendar_service.cancel_event(event.google_event_id)
    except Exception:
        pass  # mirror is authoritative; degrade silently
    try:
        deps.event_service.cancel_event(event, billable=billable)
    except Exception:
        pass
    first = client.name.split()[0]
    return {"success": True, "data": {"client": client.name},
            "message": f"Cancelei o compromisso de {first}."}


async def reschedule_event_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None,
    period: str = "this_week", new_start_time: datetime, duration_minutes: int | None = None,
) -> dict:
    if deps.calendar_service is None or deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    event, error = _find_single_event_for_client(deps, client, period)
    if error:
        return error

    new_start = _ensure_aware(new_start_time, deps.timezone)
    minutes = duration_minutes or deps.default_consult_minutes
    new_end = new_start + timedelta(minutes=minutes)
    conflicts = _find_overlaps(deps, new_start, new_end, exclude_event_id=event.id)

    is_series = event.parent_event_id is not None or event.is_recurring
    if is_series:
        template = deps.event_service.get_event(event.parent_event_id) if event.parent_event_id else event
        if template is None or not template.google_event_id:
            return _dual_write_failed()
        try:
            deps.calendar_service.update_event(template.google_event_id, start=new_start, end=new_end)
        except Exception:
            return _dual_write_failed()
        deps.event_service.reschedule_series(template, new_start, new_end, from_dt=deps.current_datetime)
    else:
        if not event.google_event_id:
            return _dual_write_failed()
        try:
            deps.calendar_service.update_event(event.google_event_id, start=new_start, end=new_end)
        except Exception:
            return _dual_write_failed()
        deps.event_service.update_event(event, start=new_start, end=new_end)

    first = client.name.split()[0]
    warning, who = _conflict_warning(deps, conflicts)
    data = {"client": client.name, "start": new_start.isoformat()}
    if who:
        data["conflict"] = True
        data["conflict_with"] = who
    return {"success": True, "data": data,
            "message": f"Remarquei {first} para {_fmt(new_start, deps.timezone)}." + warning}


async def set_session_charge_impl(
    deps: AgentDeps, *, client_name=None, client_phone=None, session_date: str, charge: bool,
) -> dict:
    if deps.event_service is None:
        return _not_connected()
    client, error = await _resolve_client(deps, client_name, client_phone)
    if error:
        return error
    from datetime import date as _date
    try:
        day = _date.fromisoformat(session_date)
    except ValueError:
        return {"success": False, "data": None,
                "message": "Não entendi a data da sessão. Use AAAA-MM-DD."}
    event = deps.event_service.find_client_session_on_date(deps.user_id, client.id, day)
    if event is None:
        first = client.name.split()[0]
        return {"success": False, "data": None,
                "message": f"Não encontrei sessão de {first} nessa data."}
    deps.event_service.set_billable(event, charge)
    first = client.name.split()[0]
    verb = "vou cobrar" if charge else "não vou cobrar"
    return {"success": True, "data": {"client": client.name, "charge": charge},
            "message": f"Pronto: {verb} a sessão de {first} nessa data."}


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
        charge: bool | None = None,
    ) -> dict:
        """Cancela o compromisso de um cliente num período. Exige cliente cadastrado.

        charge: se True, mantém a sessão cobrável mesmo cancelada.
        """
        return await cancel_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            period=period, reason=reason, charge=charge,
        )

    @agent.tool
    async def reschedule_event(
        ctx: RunContext[AgentDeps], new_start_time: str,
        client_name: str | None = None, client_phone: str | None = None,
        period: str = "this_week", duration_minutes: int | None = None,
    ) -> dict:
        """Remarca o compromisso de um cliente para um novo horário. new_start_time em ISO 8601.
        Exige cliente cadastrado e um compromisso existente no período."""
        return await reschedule_event_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            period=period, new_start_time=datetime.fromisoformat(new_start_time),
            duration_minutes=duration_minutes,
        )

    @agent.tool
    async def set_session_charge(
        ctx: RunContext[AgentDeps], session_date: str, charge: bool,
        client_name: str | None = None, client_phone: str | None = None,
    ) -> dict:
        """Define se uma sessão (cancelada/no-show) é cobrável. session_date em AAAA-MM-DD."""
        return await set_session_charge_impl(
            ctx.deps, client_name=client_name, client_phone=client_phone,
            session_date=session_date, charge=charge,
        )
