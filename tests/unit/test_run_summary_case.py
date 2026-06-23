"""run_summary_case wires SummaryInputs -> summarize_conversation (LLM-free via FunctionModel)."""

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from evals.harness import SummaryInputs, run_summary_case


def _echo_first_user(messages, info):
    # The transcript is the single user prompt build_summary_input produced.
    prompt = messages[-1].parts[-1].content
    return ModelResponse(parts=[TextPart(content=f"RESUMO::{prompt}")])


@pytest.mark.asyncio
async def test_run_summary_case_feeds_transcript_to_model():
    model = FunctionModel(_echo_first_user)
    out = await run_summary_case(
        SummaryInputs(
            existing_summary="Cliente Bruno, 200 reais.",
            messages=[("user", "passou pra 250"), ("assistant", "feito")],
        ),
        model,
    )
    assert out.startswith("RESUMO::")
    assert "Resumo anterior: Cliente Bruno, 200 reais." in out
    assert "Profissional: passou pra 250" in out
    assert "Assistente: feito" in out
