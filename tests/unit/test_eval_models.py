import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from evals.models import EVAL_MODELS, build_eval_model


@pytest.fixture(autouse=True)
def dummy_api_key(monkeypatch):
    """Set a dummy API key so model constructor doesn't error at test time (no network calls made)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-openai-key-for-tests")


def test_known_aliases_map_to_concrete_ids():
    assert EVAL_MODELS["gpt-5.4-mini"] == "gpt-5.4-mini-2026-03-17"
    assert EVAL_MODELS["gpt-5.4-nano"] == "gpt-5.4-nano"
    assert EVAL_MODELS["gpt-5.4"] == "gpt-5.4-2026-03-05"


def test_build_eval_model_returns_single_openai_model():
    m = build_eval_model("gpt-5.4-mini")
    assert isinstance(m, OpenAIChatModel)
    # the concrete model id, not the alias
    assert "gpt-5.4-mini-2026-03-17" in repr(m) or m.model_name == "gpt-5.4-mini-2026-03-17"


def test_unknown_alias_raises():
    with pytest.raises(KeyError):
        build_eval_model("does-not-exist")
