# tests/integration/test_agent_message_endpoint.py
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.api import agent_routes
from app.core.config import settings
from app.core.database import get_db
from app.main import app


# Placeholder model for agent construction (never called at request time)
def _noop_model(messages, info):
    return ModelResponse(parts=[TextPart("noop")])


def test_agent_message_returns_content(monkeypatch):
    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("Olá! Como posso ajudar com seus clientes?")])

    # Patch get_llm_model so build_simplifica_agent() doesn't require API keys,
    # then override the model at run-time via agent.override(). Mirrors the unit
    # test pattern from tests/unit/test_simplifica_agent.py.
    #
    # We use agent.override() as a context manager at the test level so that
    # __exit__ is called cleanly and avoids ContextVar warnings.
    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop_model)):
        from app.agents.simplifica_agent import build_simplifica_agent as _build
        shared_agent = _build()

    def build_with_override():
        return shared_agent

    monkeypatch.setattr(agent_routes, "build_simplifica_agent", build_with_override)
    monkeypatch.setattr(agent_routes, "ClientService", lambda db: MagicMock())
    # Keep the endpoint test network-free: don't resolve real Google calendar access.
    monkeypatch.setattr(agent_routes, "build_calendar_access", lambda db, user, settings: None)
    # Stub conversation memory (DB is mocked): empty history, no-op persistence.
    fake_history = MagicMock()
    fake_history.get_or_create_session.return_value = MagicMock(summary=None, summarized_count=0)
    fake_history.recent_messages.return_value = []
    fake_history.unsummarized_overflow.return_value = []
    monkeypatch.setattr(agent_routes, "ChatHistoryService", lambda db: fake_history)

    # Override get_db to avoid needing a real DB connection, and override the
    # model with the scripted FunctionModel at the agent level.
    app.dependency_overrides[get_db] = lambda: MagicMock()

    try:
        with shared_agent.override(model=FunctionModel(scripted)):
            client = TestClient(app)
            resp = client.post(
                f"{settings.API_PREFIX}/agent/message",
                json={"user_id": str(uuid4()), "message": "oi"},
            )
        assert resp.status_code == 200
        assert "content" in resp.json()
        assert resp.json()["content"]
    finally:
        app.dependency_overrides.clear()
