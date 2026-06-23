from pydantic_ai.messages import (
    ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from evals.harness import CaseInputs, extract_tool_calls, run_case


def test_extract_tool_calls_pairs_calls_with_returns():
    # one assistant message with a tool call, then a tool-return message
    msgs = [
        ModelResponse(parts=[ToolCallPart(tool_name="create_client", args={"name": "Ana Souza"})]),
        ModelRequest(parts=[ToolReturnPart(
            tool_name="create_client",
            content={"success": True, "data": {"name": "Ana Souza"}, "message": "ok"},
        )]),
    ]
    calls = extract_tool_calls(msgs)
    assert len(calls) == 1
    assert calls[0].name == "create_client"
    assert calls[0].args["name"] == "Ana Souza"
    assert calls[0].success is True


async def test_run_case_drives_lead_conversation_and_collects(monkeypatch):
    # Scripted model: always replies with text (no tools) so we exercise the driver,
    # not the real LLM. Build the lead agent under a patched get_llm_model.
    from unittest.mock import patch

    def reply(messages, info):
        return ModelResponse(parts=[TextPart("Oi! O Simplifica Psi te ajuda no consultório.")])

    with patch("app.agents.lead_agent.get_llm_model", return_value=FunctionModel(reply)):
        from app.agents.lead_agent import build_lead_agent  # noqa: F401  (import path proof)

    inputs = CaseInputs(agent="lead", messages=["oi", "como funciona?"])
    result = await run_case(inputs, FunctionModel(reply))

    assert result.model  # model label recorded
    assert len(result.transcript) == 2  # two user turns
    assert "Simplifica" in result.final_output
    assert result.tool_calls == []  # this scripted model called no tools
