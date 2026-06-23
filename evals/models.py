"""Pin a single OpenAI model (no FallbackModel chain) for clean per-model evals."""

from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

# alias -> concrete OpenAI model id (mirrors app/agents/foundation/llm.py)
EVAL_MODELS: dict[str, str] = {
    "gpt-5.4-mini": "gpt-5.4-mini-2026-03-17",
    "gpt-5.4-nano": "gpt-5.4-nano",
    "gpt-5.4": "gpt-5.4-2026-03-05",
}


def build_eval_model(alias: str, temperature: float = 0.1, timeout: int = 30) -> OpenAIChatModel:
    """Build a single pinned OpenAI model for `agent.override(model=...)`.

    Deterministic (seed=0, low temperature) so eval results are reproducible.
    Raises KeyError for an unknown alias.
    """
    concrete = EVAL_MODELS[alias]
    return OpenAIChatModel(
        concrete,
        settings=OpenAIChatModelSettings(timeout=timeout, temperature=temperature, seed=0),
    )
