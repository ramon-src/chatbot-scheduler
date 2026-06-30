"""Unit tests for the summarizer transcript builder (LLM-free)."""

from app.agents.summarizer import build_summary_input
from app.models.chat_session import ChatMessage


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(message_type=role, content=content)


def test_build_summary_input_maps_roles_and_header():
    text = build_summary_input(
        existing_summary="Resumo anterior aqui.",
        messages=[_msg("user", "ola"), _msg("assistant", "oi, tudo bem?")],
    )
    assert "Resumo anterior: Resumo anterior aqui." in text
    assert "Novas mensagens:" in text
    assert "Profissional: ola" in text
    assert "Assistente: oi, tudo bem?" in text


def test_build_summary_input_without_existing_summary_omits_prefix():
    text = build_summary_input(existing_summary=None, messages=[_msg("user", "ola")])
    assert "Resumo anterior:" not in text
    assert text.startswith("Novas mensagens:")
