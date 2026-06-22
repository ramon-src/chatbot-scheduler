"""Roll older conversation turns into a compact PT-BR summary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.foundation import get_llm_model
from app.core.config import settings

if TYPE_CHECKING:
    from app.models.chat_session import ChatMessage

SUMMARY_SYSTEM_PROMPT = """Você resume conversas entre um psicólogo e seu assistente de consultório.
Atualize o resumo para preservar SÓ o que ajuda a continuar a conversa: clientes mencionados,
decisões tomadas, valores/dias de cobrança, agendamentos e pendências em aberto.
Responda em Português do Brasil, em poucas frases, sem IDs, JSON, URLs ou markdown."""


def build_summary_input(existing_summary: str | None, messages: list[ChatMessage]) -> str:
    """Deterministic transcript fed to the summarizer (LLM-free, testable)."""
    lines: list[str] = []
    if existing_summary:
        lines.append(f"Resumo anterior: {existing_summary}")
    lines.append("Novas mensagens:")
    for m in messages:
        who = "Profissional" if m.message_type == "user" else "Assistente"
        lines.append(f"{who}: {m.content}")
    return "\n".join(lines)


async def summarize_conversation(
    existing_summary: str | None,
    messages: list[ChatMessage],
    model: Model | None = None,
) -> str:
    """Fold `messages` into `existing_summary` and return the updated summary."""
    agent = Agent(
        model or get_llm_model(settings.SIMPLIFICA_AGENT_MODEL, temperature=0.0, timeout=30),
        output_type=str,
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        retries=2,
    )
    result = await agent.run(build_summary_input(existing_summary, messages))
    return result.output
