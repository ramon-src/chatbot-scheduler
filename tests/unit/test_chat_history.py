"""Unit tests for chat-history conversion (DB-free)."""

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.agents.history import to_model_messages
from app.models.chat_session import ChatMessage


def _msg(message_type: str, content: str) -> ChatMessage:
    return ChatMessage(message_type=message_type, content=content)


def test_converts_user_and_assistant_rows_in_order():
    rows = [
        _msg("user", "lista meus clientes"),
        _msg("assistant", "Você tem 2 clientes ativos."),
        _msg("user", "atualize a cobrança da Ana"),
    ]

    result = to_model_messages(rows)

    assert len(result) == 3
    assert isinstance(result[0], ModelRequest)
    assert isinstance(result[0].parts[0], UserPromptPart)
    assert result[0].parts[0].content == "lista meus clientes"
    assert isinstance(result[1], ModelResponse)
    assert isinstance(result[1].parts[0], TextPart)
    assert result[1].parts[0].content == "Você tem 2 clientes ativos."
    assert isinstance(result[2], ModelRequest)


def test_skips_system_rows():
    rows = [
        _msg("system", "resumo antigo"),
        _msg("user", "oi"),
    ]

    result = to_model_messages(rows)

    assert len(result) == 1
    assert isinstance(result[0], ModelRequest)


def test_empty_history_returns_empty_list():
    assert to_model_messages([]) == []


def test_build_summary_input_includes_prior_summary_and_labels_speakers():
    from app.agents.summarizer import build_summary_input

    rows = [
        _msg("user", "cadastra a Ana"),
        _msg("assistant", "Ana cadastrada."),
    ]
    text = build_summary_input("Resumo: 2 clientes ativos.", rows)

    assert "Resumo: 2 clientes ativos." in text
    assert "Profissional: cadastra a Ana" in text
    assert "Assistente: Ana cadastrada." in text


def test_build_summary_input_without_prior_summary():
    from app.agents.summarizer import build_summary_input

    text = build_summary_input(None, [_msg("user", "oi")])

    assert "Profissional: oi" in text
    assert "Resumo anterior" not in text
