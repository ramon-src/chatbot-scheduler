import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart

from app.agents.simplifica_agent import build_simplifica_agent, SIMPLIFICA_SYSTEM_PROMPT
from app.agents.deps import AgentDeps

models.ALLOW_MODEL_REQUESTS = False  # guard: no real network


def _noop_model(messages, info):
    """Placeholder model used only for agent construction (never called)."""
    return ModelResponse(parts=[TextPart("noop")])


@pytest.mark.asyncio
async def test_agent_calls_create_client_tool_then_replies():
    """Script: first model turn calls create_client; second turn returns text."""
    calls = {"n": 0}

    async def scripted(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="create_client",
                args={"name": "Maria Silva", "phone": "+5551981321543",
                      "invoice_day": 10, "consult_price": 200.0},
            )])
        return ModelResponse(parts=[TextPart("Pronto! Cliente cadastrado. ✅")])

    # Patch get_llm_model so build_simplifica_agent() doesn't need API keys
    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop_model)):
        agent = build_simplifica_agent()

    service = MagicMock()
    created = SimpleNamespace(name="Maria Silva", phone="+5551981321543")
    service.create_client = AsyncMock(return_value=created)
    deps = AgentDeps(
        db=MagicMock(), user_id=uuid4(), user_name="Ramon",
        current_datetime=datetime(2026, 6, 21, 15, 0),
        timezone="America/Sao_Paulo", history_summary=None, client_service=service,
    )

    with agent.override(model=FunctionModel(scripted)):
        result = await agent.run("cadastra a Maria Silva, 51 98132-1543, dia 10, 200 reais", deps=deps)

    assert "cadastrado" in result.output.lower()
    service.create_client.assert_awaited_once()


def test_system_prompt_contains_required_rules():
    """Static system prompt must contain PT-BR persona and guard-rails."""
    assert "Português do Brasil" in SIMPLIFICA_SYSTEM_PROMPT
    assert "IDs" in SIMPLIFICA_SYSTEM_PROMPT
    assert "seus clientes" in SIMPLIFICA_SYSTEM_PROMPT
    assert "nome e sobrenome" in SIMPLIFICA_SYSTEM_PROMPT
