# tests/integration/test_agent_runner.py
from unittest.mock import patch
from uuid import UUID

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.user import User
from app.services import agent_runner
from app.services.agent_runner import process_professional_message

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
TEST_PHONE = "+5500000000077"


def _cleanup():
    db = SessionLocal()
    try:
        rows = db.query(ChatSession).filter(ChatSession.phone_number == TEST_PHONE).all()
        for s in rows:
            db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(
                synchronize_session=False
            )
        db.query(ChatSession).filter(ChatSession.phone_number == TEST_PHONE).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


async def test_process_persists_turn_and_returns_output(monkeypatch):
    _cleanup()
    monkeypatch.setattr(agent_runner, "build_calendar_access", lambda db, user, settings: None)

    def _noop(messages, info):
        return ModelResponse(parts=[TextPart("noop")])

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.simplifica_agent import build_simplifica_agent
        agent = build_simplifica_agent()

    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("resposta do agente")])

    db = SessionLocal()
    try:
        user = db.get(User, DEV_USER_ID)
        with agent.override(model=FunctionModel(scripted)):
            out = await process_professional_message(db, agent, user, "oi", TEST_PHONE)
        assert out == "resposta do agente"
        session = db.query(ChatSession).filter(
            ChatSession.user_id == DEV_USER_ID, ChatSession.phone_number == TEST_PHONE
        ).one()
        msgs = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.asc()).all()
        assert [m.message_type for m in msgs] == ["user", "assistant"]
        assert msgs[1].content == "resposta do agente"
    finally:
        db.close()
        _cleanup()
