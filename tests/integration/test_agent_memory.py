# tests/integration/test_agent_memory.py
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.api import agent_routes
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.chat_session import ChatMessage, ChatSession

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
TEST_PHONE = "+5500000000001"


def _noop_model(messages, info):
    return ModelResponse(parts=[TextPart("noop")])


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


def test_endpoint_persists_turn_and_replays_history(monkeypatch):
    _cleanup()
    seen: list[int] = []

    async def scripted(messages, info):
        seen.append(len(messages))
        return ModelResponse(parts=[TextPart("ok")])

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop_model)):
        from app.agents.simplifica_agent import build_simplifica_agent as _build
        shared_agent = _build()

    monkeypatch.setattr(agent_routes, "build_simplifica_agent", lambda: shared_agent)
    monkeypatch.setattr(agent_routes, "build_calendar_access", lambda db, user, settings: None)

    try:
        with shared_agent.override(model=FunctionModel(scripted)):
            client = TestClient(app)
            r1 = client.post(
                f"{settings.API_PREFIX}/agent/message",
                json={"user_id": str(DEV_USER_ID), "message": "lista meus clientes", "phone_number": TEST_PHONE},
            )
            r2 = client.post(
                f"{settings.API_PREFIX}/agent/message",
                json={"user_id": str(DEV_USER_ID), "message": "atualize a cobrança", "phone_number": TEST_PHONE},
            )

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Second run must replay the first turn -> more messages than the first run.
        assert seen[1] > seen[0]

        # Both turns persisted (2 messages each = 4 rows) under one session.
        db = SessionLocal()
        try:
            sessions = db.query(ChatSession).filter(
                ChatSession.user_id == DEV_USER_ID, ChatSession.phone_number == TEST_PHONE
            ).all()
            assert len(sessions) == 1
            msgs = db.query(ChatMessage).filter(
                ChatMessage.session_id == sessions[0].id
            ).order_by(ChatMessage.created_at.asc()).all()
            assert [m.message_type for m in msgs] == ["user", "assistant", "user", "assistant"]
            assert msgs[0].content == "lista meus clientes"
        finally:
            db.close()
    finally:
        _cleanup()


def test_overflow_messages_are_folded_into_the_rolling_summary(monkeypatch):
    """Once the conversation exceeds the raw window, older turns are folded into
    the session summary (summarize_conversation called; summarized_count advances)."""
    _cleanup()

    summary_calls: list[int] = []

    async def fake_summarize(existing_summary, pending, model=None):
        summary_calls.append(len(pending))
        return "RESUMO: profissional conversando sobre clientes."

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop_model)):
        from app.agents.simplifica_agent import build_simplifica_agent as _build
        shared_agent = _build()

    monkeypatch.setattr(agent_routes, "build_simplifica_agent", lambda: shared_agent)
    monkeypatch.setattr(agent_routes, "build_calendar_access", lambda db, user, settings: None)
    # Don't hit the real LLM for summaries — fold deterministically.
    monkeypatch.setattr(agent_routes, "summarize_conversation", AsyncMock(side_effect=fake_summarize))

    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("ok")])

    try:
        with shared_agent.override(model=FunctionModel(scripted)):
            client = TestClient(app)
            # 6 turns = 12 messages > RAW_HISTORY_LIMIT (10) -> overflow folded.
            for i in range(6):
                r = client.post(
                    f"{settings.API_PREFIX}/agent/message",
                    json={"user_id": str(DEV_USER_ID), "message": f"mensagem {i}", "phone_number": TEST_PHONE},
                )
                assert r.status_code == 200

        assert summary_calls, "summarize_conversation was never called despite overflow"

        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.user_id == DEV_USER_ID, ChatSession.phone_number == TEST_PHONE
            ).one()
            assert session.summary == "RESUMO: profissional conversando sobre clientes."
            assert session.summarized_count > 0
        finally:
            db.close()
    finally:
        _cleanup()
