import pytest
from pydantic_ai.models.fallback import FallbackModel
from app.agents.foundation import get_llm_model


@pytest.fixture(autouse=True)
def dummy_api_keys(monkeypatch):
    """Set dummy API keys so model constructors don't error at test time (no network calls made)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-openai-key-for-tests")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-dummy-openrouter-key-for-tests")


def test_get_llm_model_returns_fallback():
    model = get_llm_model("gpt-5.4-mini", temperature=0.1, timeout=15)
    assert isinstance(model, FallbackModel)


def test_unknown_model_falls_back_to_default():
    model = get_llm_model("nonexistent-model")
    assert isinstance(model, FallbackModel)


def test_openrouter_skipped_when_no_key(monkeypatch):
    """Regression: aliases whose chain includes OpenRouter must still build as an
    OpenAI-only FallbackModel when no OPENROUTER_API_KEY is set, instead of raising
    UserError at construction. Lets the same aliases work with only an OpenAI key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    model = get_llm_model("gpt-5.4-mini", temperature=0.1, timeout=15)
    assert isinstance(model, FallbackModel)
    from pydantic_ai.models.openrouter import OpenRouterModel

    assert not any(isinstance(m, OpenRouterModel) for m in model.models)
