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

@pytest.mark.skip(reason=READY)
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


@pytest.mark.skip(reason=READY)
async def test_list_empty_period_says_so(live):
    """Período sem compromissos → list_events success, total 0, mensagem amigável."""
    result = await live.send("o que eu tenho mês que vem?")
    lists = live.tool_returns(result, "list_events")
    assert lists, f"list_events não foi chamada. output: {result.output!r}"
    assert lists[-1]["data"]["total"] == 0
    assert "não tem" in lists[-1]["message"].lower() or "nenhum" in lists[-1]["message"].lower()


@pytest.mark.skip(reason=READY)
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


@pytest.mark.skip(reason=READY)
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
    assert cancels and cancels[-1]["success"] is False, "cancelou apesar da ambiguidade"
    active_after = live.db.query(Event).filter(
        Event.user_id == live.user_id, Event.status != "cancelled"
    ).count()
    assert active_after == active_before, "cancelou algo num caso ambíguo"


# =============================================================================
# CLIENTES — READY (tools já existem)
# =============================================================================

@pytest.mark.skip(reason=READY)
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


@pytest.mark.skip(reason=READY)
async def test_list_clients(live):
    """'quem são meus clientes?' → list_clients success, inclui a Maria."""
    result = await live.send("quem são meus clientes?")
    lists = live.tool_returns(result, "list_clients")
    assert lists and lists[-1]["success"] is True, f"output: {result.output!r}"
    assert any("Maria" in n for n in lists[-1]["data"]["names"])


@pytest.mark.skip(reason=READY)
async def test_update_client_price(live):
    """'muda o valor da consulta da Maria pra 250' → update_client; preço no banco = 250."""
    from app.models.client import Client

    result = await live.send(f"muda o valor da consulta da {live.client_name} para 250 reais")
    updates = live.tool_returns(result, "update_client")
    assert updates and updates[-1]["success"] is True, f"output: {result.output!r}"
    c = live.db.query(Client).filter(Client.phone == live.client_phone).first()
    live.db.refresh(c)
    assert c.consult_price == Decimal("250")


@pytest.mark.skip(reason=READY)
async def test_find_client_returns_phone(live):
    """'qual o telefone da Maria Silva?' → find_client retorna o telefone."""
    result = await live.send(f"qual o telefone da {live.client_name}?")
    finds = live.tool_returns(result, "find_client")
    assert finds and finds[-1]["success"] is True, f"output: {result.output!r}"
    assert finds[-1]["data"]["phone"] == live.client_phone


@pytest.mark.skip(reason=READY)
async def test_deactivate_client(live):
    """'desativa a Maria' → deactivate_client; is_active=False no banco."""
    from app.models.client import Client

    result = await live.send(f"desativa a {live.client_name}, ela não atende mais comigo")
    deact = live.tool_returns(result, "deactivate_client")
    assert deact and deact[-1]["success"] is True, f"output: {result.output!r}"
    c = live.db.query(Client).filter(Client.phone == live.client_phone).first()
    live.db.refresh(c)
    assert c.is_active is False


@pytest.mark.skip(reason=READY)
async def test_duplicate_phone_is_rejected(live):
    """Cadastrar com telefone já existente → create_client success=False (conflito)."""
    result = await live.send(
        f"cadastra o João Teste, telefone {live.client_phone}, dia 5, consulta 100 reais"
    )
    creates = live.tool_returns(result, "create_client")
    assert creates and creates[-1]["success"] is False, "aceitou telefone duplicado"


@pytest.mark.skip(reason=READY)
async def test_invalid_phone_is_rejected(live):
    """Telefone inválido → create_client success=False (validação)."""
    result = await live.send("cadastra o Pedro Lima, telefone 123, dia 5, consulta 100 reais")
    creates = live.tool_returns(result, "create_client")
    if creates:
        assert creates[-1]["success"] is False, "aceitou telefone inválido"


# =============================================================================
# BLOQUEADOS POR FEATURE (habilitar depois de construir a capacidade)
# =============================================================================

@pytest.mark.skip(reason=_feature("tool de reagendamento (update_event) ainda não exposta ao agente"))
async def test_reschedule_event(live):
    """'muda a sessão da Maria de amanhã para as 15h' → atualiza o horário do evento."""
    from app.models.event import Event

    await live.send(f"agenda a {live.client_name} amanhã às 10h")
    result = await live.send(f"muda a sessão da {live.client_name} de amanhã para as 15h")
    updates = live.tool_returns(result, "update_event")
    assert updates and updates[-1]["success"] is True, f"output: {result.output!r}"
    ev = (
        live.db.query(Event)
        .filter(Event.user_id == live.user_id, Event.status != "cancelled")
        .order_by(Event.created_at.desc())
        .first()
    )
    assert ev.start_time.astimezone(live.tz).hour == 15


@pytest.mark.skip(reason=_feature("sem detecção de conflito de horário"))
async def test_conflict_detection_warns(live):
    """Agendar dois clientes no mesmo horário → o agente deve avisar/recusar o conflito."""
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
        # comportamento-alvo: a segunda criação é barrada por conflito
        assert creates and creates[-1]["success"] is False
    finally:
        live.db.delete(other)
        live.db.commit()


@pytest.mark.skip(reason=_feature("Plano 3 — cobrança (mark_paid) não implementado"))
async def test_billing_mark_paid(live):
    """'marca como paga a consulta da Maria' → mark_paid; pagamento registrado."""
    await live.send(f"agenda a {live.client_name} amanhã às 10h")
    result = await live.send(f"marca como paga a consulta da {live.client_name} de amanhã")
    paid = live.tool_returns(result, "mark_paid")
    assert paid and paid[-1]["success"] is True


@pytest.mark.skip(reason=_feature("Plano 3 — cobrança (list_pending_payments) não implementado"))
async def test_billing_list_pending(live):
    """'quem está devendo este mês?' → list_pending_payments."""
    result = await live.send("quem está devendo este mês?")
    pending = live.tool_returns(result, "list_pending_payments")
    assert pending and pending[-1]["success"] is True


@pytest.mark.skip(reason=_feature("Plano 3 — cobrança (send_payment_reminder) não implementado"))
async def test_billing_send_reminder(live):
    """'manda um lembrete de cobrança pra Maria' → send_payment_reminder."""
    result = await live.send(f"manda um lembrete de cobrança pra {live.client_name}")
    reminder = live.tool_returns(result, "send_payment_reminder")
    assert reminder and reminder[-1]["success"] is True
