"""Roll older conversation turns into a compact PT-BR summary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.foundation import get_llm_model
from app.core.config import settings

if TYPE_CHECKING:
    from app.models.chat_session import ChatMessage

SUMMARY_SYSTEM_PROMPT = """Você mantém um resumo vivo da conversa entre um psicólogo e seu assistente de consultório.
A cada rodada você recebe o resumo anterior e as novas mensagens e devolve o resumo ATUALIZADO.

PRESERVE (núcleo — mantenha SEMPRE, mesmo enxugando):
- Clientes ativos e seus dados finais: nome, telefone, dia de cobrança, preço da consulta.
- Agendamentos válidos: cliente, data e hora.
- Pendências em aberto e acionáveis (ex.: "cadastro da Ana aguardando o telefone").

FAÇA FAXINA (corrija e descarte ao dobrar):
- Fora de domínio: descarte qualquer trecho que não seja sobre clientes, agenda ou cobrança
  (programação, SQL, banco de dados, devops, assuntos gerais), inclusive a recusa do assistente. Não vira memória.
- Dado substituído: se um valor foi corrigido (ex.: preço 200 e depois 250, telefone trocado),
  mantenha SÓ o valor final; o antigo some.
- Fio morto: tentativas superadas ou que não levaram a nada saem.
- Vazamento técnico: nunca inclua IDs, códigos, JSON, URLs ou markdown.

VIÉS: na dúvida entre manter um detalhe de borda ou enxugar, enxugue. Mas pendência acionável
NÃO é fio morto — preserve.

FORMATO: Português do Brasil, poucas frases, texto simples, sem IDs, JSON, URLs ou markdown."""


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
