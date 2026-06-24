"""Convert persisted chat rows into pydantic-ai message history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

if TYPE_CHECKING:
    from app.models.chat_session import ChatMessage


def to_model_messages(rows: list[ChatMessage]) -> list[ModelMessage]:
    """Map stored chat rows to pydantic-ai history.

    'user' -> ModelRequest(UserPromptPart); 'assistant' -> ModelResponse(TextPart).
    'system' rows are skipped (the live system prompt is rebuilt per run).
    """
    messages: list[ModelMessage] = []
    for row in rows:
        if row.message_type == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=row.content)]))
        elif row.message_type == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=row.content)]))
    return messages
