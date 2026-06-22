# tests/integration/test_lead_runner.py
from unittest.mock import patch

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.lead import Lead
from app.services.agent_runner import process_lead_message
from app.services.lead_service import LeadService

LEAD_PHONE = "5551900000040"


def _reply_model(text):
    async def fn(messages, info):
        return ModelResponse(parts=[TextPart(text)])
    return FunctionModel(fn)


def _build_lead_agent_with_noop():
    with patch("app.agents.lead_agent.get_llm_model", return_value=_reply_model("noop")):
        from app.agents.lead_agent import build_lead_agent
        return build_lead_agent()


def _cleanup(db):
    leads = db.query(Lead).filter(Lead.phone == LEAD_PHONE).all()
    for lead in leads:
        for s in db.query(ChatSession).filter(ChatSession.lead_id == lead.id):
            db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.lead_id == lead.id).delete(synchronize_session=False)
    db.query(Lead).filter(Lead.phone == LEAD_PHONE).delete(synchronize_session=False)
    db.commit()


async def test_process_lead_message_persists_turn_in_lead_session():
    db = SessionLocal()
    try:
        _cleanup(db)
        lead = LeadService(db).get_or_create_lead(LEAD_PHONE)
        agent = _build_lead_agent_with_noop()
        with agent.override(model=_reply_model("Oi! Posso te explicar o Simplifica Psi.")):
            reply = await process_lead_message(db, agent, lead, "o que é isso?", LEAD_PHONE)
        assert "Simplifica" in reply
        session = db.query(ChatSession).filter(ChatSession.lead_id == lead.id).first()
        assert session is not None and session.user_id is None
        msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()
        assert msgs == 2  # user + assistant
    finally:
        _cleanup(db)
        db.close()
