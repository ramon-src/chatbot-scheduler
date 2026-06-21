# tests/unit/test_config_agent_settings.py
from app.core.config import settings

def test_agent_settings_have_defaults():
    assert settings.SIMPLIFICA_AGENT_MODEL  # non-empty
    assert settings.TIMEZONE == "America/Sao_Paulo"
    # OPENROUTER_API_KEY is optional, attribute must exist
    assert hasattr(settings, "OPENROUTER_API_KEY")
