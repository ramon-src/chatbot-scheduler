# tests/integration/test_agent_message_endpoint.py
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart

from app.main import app
from app.api import agent_routes
from app.core.config import settings
from app.core.database import get_db

models.ALLOW_MODEL_REQUESTS = False

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
