"""Live functional scenario BACKLOG (real LLM + Google).

Every test here is skip-marked on purpose — it documents an expected behavior
to enable/implement later, with concrete assertions so it is runnable the moment
its skip is removed. Two kinds of skip reason:

  READY    — the current tools already support this; remove the skip to run it
             live (it should pass as-is).
  FEATURE  — needs a capability we have not built yet; remove the skip after
             building that feature.

They reuse the `live` fixture from tests/live/conftest.py (which exposes
live.send / live.db / live.tool_returns / live.tz / live.user_id /
live.client_name / live.client_phone). Run a single one while iterating with:

    RUN_LIVE=1 uv run pytest -m live -s -v -k recurring
"""

import logging
from datetime import timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.live

for _noisy in ("httpx", "httpcore", "openai", "google_auth_httplib2", "googleapiclient"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Skip-reason conventions:
READY = "PENDENTE (pronto): habilitar quando formos rodar a bateria live — as tools já existem"


def _feature(what: str) -> str:
    return f"PENDENTE (feature): {what}"


# =============================================================================
# AGENDA — READY (tools já existem)
# =============================================================================

async def test_schedule_with_explicit_duration(live):
    """'sessão de 30 minutos' → create_event com duração de 30 min no banco."""
    from app.models.event import Event

    result = await live.send(f"agenda a {live.client_name} amanhã às 14h, sessão de 30 minutos")
    creates = live.tool_returns(result, "create_event")
    assert creates and creates[-1]["success"] is True, f"output: {result.output!r}"

    ev = (
        live.db.query(Event)
        .filter(Event.user_id == live.user_id, Event.status != "cancelled")
        .order_by(Event.created_at.desc())
        .first()
    )
    assert ev is not None
    assert (ev.end_time - ev.start_time) == timedelta(minutes=30)


async def test_list_empty_period_says_so(live):
    """Período sem compromissos → list_events success, total 0, mensagem amigável.

    Uses 'próxima semana' (a supported, reliably-empty period — no scenario
    schedules next week); 'mês que vem' isn't a period the list tool understands,
    so the agent answers in plain text without calling list_events."""
    result = await live.send("o que eu tenho na próxima semana?")
    lists = live.tool_returns(result, "list_events")
    assert lists, f"list_events não foi chamada. output: {result.output!r}"
    assert lists[-1]["data"]["total"] == 0
    assert "não tem" in lists[-1]["message"].lower() or "nenhum" in lists[-1]["message"].lower()


async def test_homonym_requires_phone(live):
    """Dois clientes 'Maria *' → agente pede telefone; NÃO cria evento órfão."""
    from app.models.client import Client
    from app.models.event import Event

    extra = Client(
        user_id=live.user_id, name="Maria Santos", phone="+5551988887777",
        invoice_day=5, consult_price=Decimal("180"), is_active=True,
    )
    live.db.add(extra)
    live.db.commit()
    try:
        before = live.db.query(Event).filter(Event.user_id == live.user_id).count()
        result = await live.send("agenda a Maria amanhã às 11h")
        creates = live.tool_returns(result, "create_event")
        if creates:
            assert creates[-1]["success"] is False, "agendou sem desambiguar o homônimo"
        after = live.db.query(Event).filter(Event.user_id == live.user_id).count()
        assert after == before, "criou evento sem resolver qual Maria"
    finally:
        live.db.delete(extra)
        live.db.commit()


async def test_cancel_ambiguous_asks_for_day(live):
    """Dois compromissos no mesmo período → cancelamento pede o dia exato, não cancela."""
    from app.models.event import Event

    await live.send(f"agenda a {live.client_name} amanhã às 10h")
    await live.send(f"agenda a {live.client_name} amanhã às 15h")
    active_before = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status != "cancelled"
    ).count()
    assert active_before >= 2

    result = await live.send(f"cancela a sessão da {live.client_name} essa semana")
    cancels = live.tool_returns(result, "cancel_event")
    # Correct behavior is EITHER: the agent asks for the exact day in plain text
    # (cancel_event never called -> cancels == []), OR it calls cancel_event and
    # gets an ambiguity refusal (success False). Both must leave nothing cancelled.
    if cancels:
        assert cancels[-1]["success"] is False, "cancelou apesar da ambiguidade"
    active_after = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status != "cancelled"
    ).count()
    assert active_after == active_before, "cancelou algo num caso ambíguo"


# =============================================================================
# CLIENTES — READY (tools já existem)
# =============================================================================

async def test_create_client(live):
    """'cadastra a Ana Souza, ...' → create_client success; cliente no banco."""
    from app.models.client import Client

    result = await live.send(
        "cadastra a Ana Souza, telefone 51 98765-4321, dia de cobrança 15, consulta 220 reais"
    )
    creates = live.tool_returns(result, "create_client")
    assert creates and creates[-1]["success"] is True, f"output: {result.output!r}"
    ana = live.db.query(Client).filter(
        Client.user_id == live.user_id, Client.name.ilike("%Ana Souza%")
    ).first()
    assert ana is not None and ana.is_active is True


async def test_list_clients(live):
    """'quem são meus clientes?' → list_clients success, inclui a Maria."""
    result = await live.send("quem são meus clientes?")
    lists = live.tool_returns(result, "list_clients")
    assert lists and lists[-1]["success"] is True, f"output: {result.output!r}"
    assert any("Maria" in n for n in lists[-1]["data"]["names"])


async def test_update_client_price(live):
    """'muda o valor da consulta da Maria pra 250' → update_client; preço no banco = 250."""
    from app.models.client import Client

    result = await live.send(f"muda o valor da consulta da {live.client_name} para 250 reais")
    updates = live.tool_returns(result, "update_client")
    assert updates and updates[-1]["success"] is True, f"output: {result.output!r}"
    c = live.db.query(Client).filter(Client.phone == live.client_phone).first()
    live.db.refresh(c)
    assert c.consult_price == Decimal("250")


async def test_find_client_returns_phone(live):
    """'qual o telefone da Maria Silva?' → find_client retorna o telefone."""
    result = await live.send(f"qual o telefone da {live.client_name}?")
    finds = live.tool_returns(result, "find_client")
    assert finds and finds[-1]["success"] is True, f"output: {result.output!r}"
    assert finds[-1]["data"]["phone"] == live.client_phone


async def test_duplicate_phone_is_rejected(live):
    """Cadastrar com telefone já existente → create_client success=False (conflito)."""
    result = await live.send(
        f"cadastra o João Teste, telefone {live.client_phone}, dia 5, consulta 100 reais"
    )
    creates = live.tool_returns(result, "create_client")
    assert creates and creates[-1]["success"] is False, "aceitou telefone duplicado"


async def test_invalid_phone_is_rejected(live):
    """Telefone inválido → create_client success=False (validação)."""
    result = await live.send("cadastra o Pedro Lima, telefone 123, dia 5, consulta 100 reais")
    creates = live.tool_returns(result, "create_client")
    if creates:
        assert creates[-1]["success"] is False, "aceitou telefone inválido"


async def test_deactivate_client(live):
    """'desativa a Maria' → deactivate_client; is_active=False no banco.

    Runs LAST: it deactivates the shared Maria, so any test needing her active
    (e.g. the duplicate-phone conflict check) must run before it."""
    from app.models.client import Client

    result = await live.send(
        f"desativa a minha cliente {live.client_name}, telefone {live.client_phone}, "
        f"ela não atende mais comigo. É ela mesma, pode desativar direto."
    )
    deact = live.tool_returns(result, "deactivate_client")
    assert deact and deact[-1]["success"] is True, f"output: {result.output!r}"
    c = live.db.query(Client).filter(Client.phone == live.client_phone).first()
    live.db.refresh(c)
    assert c.is_active is False


# =============================================================================
# BLOQUEADOS POR FEATURE (habilitar depois de construir a capacidade)
# =============================================================================

async def test_reschedule_event(live):
    """'muda a sessão da Maria de amanhã para as 17h' → reschedule_event + resposta "Remarquei".

    Uses 8h→17h to avoid the 10h/15h slots reserved by test_cancel_ambiguous_asks_for_day
    and test_conflict_detection_warns (which both create events at 10h under the same
    module-scoped fixture, causing the agent to find multiple 10h events and ask for
    disambiguation instead of rescheduling).
    """
    from app.models.client import Client
    from app.models.event import Event

    client = live.db.query(Client).filter(
        Client.user_id == live.user_id, Client.name == live.client_name
    ).first()

    await live.send(f"agenda a {live.client_name} amanhã às 8h")
    result = await live.send(f"muda a sessão da {live.client_name} de amanhã para as 17h")
    updates = live.tool_returns(result, "reschedule_event")
    assert updates and updates[-1]["success"] is True, f"output: {result.output!r}"
    assert "remarquei" in result.output.lower(), f"expected 'Remarquei' in output: {result.output!r}"
    ev = (
        live.db.query(Event)
        .filter(
            Event.user_id == live.user_id,
            Event.client_id == client.id,
            Event.status != "cancelled",
        )
        .order_by(Event.created_at.desc())
        .first()
    )
    assert ev.start_time.astimezone(live.tz).hour == 17


async def test_conflict_detection_warns(live):
    """Agendar dois clientes no mesmo horário → warn-not-block: evento criado + "Atenção" na resposta."""
    from app.models.client import Client

    other = Client(
        user_id=live.user_id, name="João Pereira", phone="+5551977776666",
        invoice_day=8, consult_price=Decimal("200"), is_active=True,
    )
    live.db.add(other)
    live.db.commit()
    try:
        await live.send(f"agenda a {live.client_name} amanhã às 10h")
        result = await live.send("agenda o João Pereira amanhã às 10h")
        creates = live.tool_returns(result, "create_event")
        # warn-not-block: o segundo evento deve ser criado (success=True) com aviso
        assert creates and creates[-1]["success"] is True, (
            f"expected conflict to WARN not block; output: {result.output!r}"
        )
        assert "atenção" in result.output.lower(), (
            f"expected 'Atenção' warning in output: {result.output!r}"
        )
    finally:
        live.db.delete(other)
        live.db.commit()


async def test_billing_mark_paid(live):
    """Seed a past pending session at 7h → 'marca como pago o mês da Maria' → mark_paid success.

    Seeds the event directly in the DB (no Google Calendar needed for billing).
    Uses hour 7 to avoid cross-test collisions with the other scenarios in this
    module-scoped fixture (other tests use 8h, 9h, 10h, 14h, 15h, 17h).
    Client billing_mode defaults to 'monthly' (server_default).
    """
    from datetime import datetime, timedelta

    from app.models.calendar import Calendar
    from app.models.client import Client
    from app.models.event import Event, EventStatus, PaymentStatus

    client = live.db.query(Client).filter(
        Client.user_id == live.user_id, Client.name == live.client_name
    ).first()
    calendar = (
        live.db.query(Calendar)
        .filter(Calendar.user_id == live.user_id, Calendar.is_primary == True)  # noqa: E712
        .first()
    )
    if calendar is None:
        from app.services.event_service import EventService
        calendar = EventService(live.db).get_primary_calendar(live.user_id)

    yesterday_7h = (
        datetime.now(live.tz).replace(hour=7, minute=0, second=0, microsecond=0)
        - timedelta(days=1)
    )
    ev = Event(
        user_id=live.user_id, client_id=client.id, calendar_id=calendar.id,
        title=f"Sessão {live.client_name}", google_event_id=f"billing-test-mark-paid-7h",
        start_time=yesterday_7h, end_time=yesterday_7h + timedelta(hours=1),
        price=Decimal("200"), billable=True,
        status=EventStatus.SCHEDULED.value,
        payment_status=PaymentStatus.PENDING.value,
    )
    live.db.add(ev)
    live.db.commit()

    try:
        result = await live.send(
            f"marca como pago o mês da {live.client_name}, telefone {live.client_phone}"
        )
        paid = live.tool_returns(result, "mark_paid")
        assert paid and paid[-1]["success"] is True, (
            f"mark_paid not called or failed. output: {result.output!r} tool_returns: {paid!r}"
        )
        live.db.refresh(ev)
        assert ev.payment_status == PaymentStatus.PAID.value, (
            f"event payment_status not updated: {ev.payment_status!r}"
        )
    finally:
        live.db.delete(ev)
        live.db.commit()


async def test_billing_list_pending(live):
    """Seed a past pending session at 7h → 'quem está em aberto?' → list_pending_payments names client.

    Uses hour 7 to avoid cross-test collisions (same isolation strategy as mark_paid).
    """
    from datetime import datetime, timedelta

    from app.models.calendar import Calendar
    from app.models.client import Client
    from app.models.event import Event, EventStatus, PaymentStatus

    client = live.db.query(Client).filter(
        Client.user_id == live.user_id, Client.name == live.client_name
    ).first()
    calendar = (
        live.db.query(Calendar)
        .filter(Calendar.user_id == live.user_id, Calendar.is_primary == True)  # noqa: E712
        .first()
    )
    if calendar is None:
        from app.services.event_service import EventService
        calendar = EventService(live.db).get_primary_calendar(live.user_id)

    yesterday_7h = (
        datetime.now(live.tz).replace(hour=7, minute=0, second=0, microsecond=0)
        - timedelta(days=1)
    )
    ev = Event(
        user_id=live.user_id, client_id=client.id, calendar_id=calendar.id,
        title=f"Sessão {live.client_name}", google_event_id=f"billing-test-list-pending-7h",
        start_time=yesterday_7h, end_time=yesterday_7h + timedelta(hours=1),
        price=Decimal("200"), billable=True,
        status=EventStatus.SCHEDULED.value,
        payment_status=PaymentStatus.PENDING.value,
    )
    live.db.add(ev)
    live.db.commit()

    try:
        result = await live.send("quem está em aberto?")
        pending = live.tool_returns(result, "list_pending_payments")
        assert pending and pending[-1]["success"] is True, (
            f"list_pending_payments not called or failed. output: {result.output!r} tool_returns: {pending!r}"
        )
        first_name = live.client_name.split()[0]
        assert first_name in result.output, (
            f"client name '{first_name}' not in agent reply: {result.output!r}"
        )
    finally:
        live.db.delete(ev)
        live.db.commit()


async def test_billing_send_reminder(live):
    """Seed a past pending session at 7h → 'manda um lembrete pra Maria' → send_payment_reminder called.

    The reminder targets live.client_phone (controlled test number — not a real patient).
    Uses hour 7 for isolation (same strategy as the other billing tests).
    Asserts the tool was called and the agent confirms ('Enviei').
    """
    from datetime import datetime, timedelta

    from app.models.calendar import Calendar
    from app.models.client import Client
    from app.models.event import Event, EventStatus, PaymentStatus

    client = live.db.query(Client).filter(
        Client.user_id == live.user_id, Client.name == live.client_name
    ).first()
    calendar = (
        live.db.query(Calendar)
        .filter(Calendar.user_id == live.user_id, Calendar.is_primary == True)  # noqa: E712
        .first()
    )
    if calendar is None:
        from app.services.event_service import EventService
        calendar = EventService(live.db).get_primary_calendar(live.user_id)

    yesterday_7h = (
        datetime.now(live.tz).replace(hour=7, minute=0, second=0, microsecond=0)
        - timedelta(days=1)
    )
    ev = Event(
        user_id=live.user_id, client_id=client.id, calendar_id=calendar.id,
        title=f"Sessão {live.client_name}", google_event_id=f"billing-test-reminder-7h",
        start_time=yesterday_7h, end_time=yesterday_7h + timedelta(hours=1),
        price=Decimal("200"), billable=True,
        status=EventStatus.SCHEDULED.value,
        payment_status=PaymentStatus.PENDING.value,
    )
    live.db.add(ev)
    live.db.commit()

    try:
        result = await live.send(
            f"manda um lembrete de cobrança pra {live.client_name}, "
            f"telefone {live.client_phone}"
        )
        reminder = live.tool_returns(result, "send_payment_reminder")
        assert reminder and reminder[-1]["success"] is True, (
            f"send_payment_reminder not called or failed. output: {result.output!r} "
            f"tool_returns: {reminder!r}"
        )
        assert "enviei" in result.output.lower(), (
            f"expected 'Enviei' in agent reply: {result.output!r}"
        )
    finally:
        live.db.delete(ev)
        live.db.commit()
