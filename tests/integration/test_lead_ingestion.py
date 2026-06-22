from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.channels.inbound import InboundMessage
from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.inbound_message import InboundMessageRecord
from app.models.lead import Lead
from app.services import ingestion_service
from app.services.ingestion_service import IngestionService, dispatch_lead_run

LEAD_PHONE = "5551900000050"
MSG_ID = "lead-ingest-msg-1"


def _inbound():
    return InboundMessage(
        provider="evolution", sender_phone=LEAD_PHONE, text="oi, o que é o simplifica?",
        provider_message_id=MSG_ID, timestamp=datetime(2026, 6, 22, 12, 0, tzinfo=UTC),
        recipient_phone=None, raw={"event": "messages.upsert"},
    )


def _noop(messages, info):
    return ModelResponse(parts=[TextPart("noop")])


def _build_lead_agent_with_noop():
    # Build with a FunctionModel so construction needs no real LLM creds; the actual
    # scripted reply is supplied per-call via agent.override(...).
    with patch("app.agents.lead_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.lead_agent import build_lead_agent
        return build_lead_agent()


def _scripted(text):
    async def fn(messages, info):
        return ModelResponse(parts=[TextPart(text)])
    return FunctionModel(fn)


def _cleanup(db):
    db.query(InboundMessageRecord).filter(
        InboundMessageRecord.provider_message_id == MSG_ID
    ).delete(synchronize_session=False)
    for lead in db.query(Lead).filter(Lead.phone == LEAD_PHONE).all():
        for s in db.query(ChatSession).filter(ChatSession.lead_id == lead.id):
            db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.lead_id == lead.id).delete(synchronize_session=False)
    db.query(Lead).filter(Lead.phone == LEAD_PHONE).delete(synchronize_session=False)
    db.commit()


async def test_lead_inbound_runs_agent_creates_lead_and_sends_reply(monkeypatch):
    db = SessionLocal()
    try:
        _cleanup(db)
        result = IngestionService(db).handle(_inbound())
        assert result.status == "lead" and result.record_id is not None
        record_id = result.record_id
    finally:
        db.close()

    agent = _build_lead_agent_with_noop()
    monkeypatch.setattr(ingestion_service, "build_lead_agent", lambda: agent)
    sender = MagicMock()
    sender.send.return_value = True
    monkeypatch.setattr(ingestion_service, "EvolutionOutboundAdapter", lambda settings: sender)

    with agent.override(model=_scripted("Oi! O Simplifica Psi te ajuda no consultório.")):
        await dispatch_lead_run(_inbound(), record_id)

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.phone == LEAD_PHONE).first()
        assert lead is not None
        session = db.query(ChatSession).filter(ChatSession.lead_id == lead.id).first()
        assert session is not None and session.user_id is None
        sender.send.assert_called_once()
        sent = sender.send.call_args[0][0]
        assert sent.to_phone == LEAD_PHONE and "Simplifica" in sent.text
    finally:
        _cleanup(db)
        db.close()


async def test_lead_dispatch_is_claimed_once(monkeypatch):
    db = SessionLocal()
    try:
        _cleanup(db)
        result = IngestionService(db).handle(_inbound())
        record_id = result.record_id
    finally:
        db.close()

    agent = _build_lead_agent_with_noop()
    monkeypatch.setattr(ingestion_service, "build_lead_agent", lambda: agent)
    monkeypatch.setattr(
        ingestion_service, "EvolutionOutboundAdapter",
        lambda settings: MagicMock(send=MagicMock(return_value=True)),
    )

    with agent.override(model=_scripted("ok")):
        await dispatch_lead_run(_inbound(), record_id)
        await dispatch_lead_run(_inbound(), record_id)  # second claims nothing

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.phone == LEAD_PHONE).first()
        session = db.query(ChatSession).filter(ChatSession.lead_id == lead.id).first()
        msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()
        assert msgs == 2
    finally:
        _cleanup(db)
        db.close()
