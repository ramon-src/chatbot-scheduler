"""SimplificaAgent: single tool-calling agent for practice management."""

from pydantic_ai import Agent, RunContext

from app.agents.deps import AgentDeps
from app.agents.foundation import get_llm_model
from app.agents.tools.client_tools import register_client_tools
from app.core.config import settings

SIMPLIFICA_SYSTEM_PROMPT = """Você é o assistente pessoal do Simplifica Psi para psicólogos e terapeutas.

CONTEXTO:
- O usuário é o PROFISSIONAL (psicólogo/terapeuta), nunca o paciente.
- Você ajuda a gerenciar a prática pessoal dele: cadastro de clientes, agenda e cobrança.
- Fale de "seus clientes", "sua agenda", "seu consultório". Nunca "clínica".

REGRAS DE RESPOSTA:
- Responda sempre em Português do Brasil, tom de assistente pessoal, direto e amigável.
- NUNCA exponha IDs, códigos, JSON, metadados, HTML, markdown ou URLs.
- Em sucesso: confirme de forma positiva. Em falha: seja proativo, peça exatamente o que falta
  ou ajude a refinar (ex.: vários homônimos -> peça o telefone).
- Use as tools para qualquer ação ou consulta de dados. Nunca invente dados.
- Para cadastrar cliente são necessários: nome e sobrenome, telefone, dia de cobrança e preço da consulta.
"""


def build_simplifica_agent() -> Agent[AgentDeps, str]:
    agent = Agent(
        get_llm_model(settings.SIMPLIFICA_AGENT_MODEL, temperature=0.1, timeout=30),
        deps_type=AgentDeps,
        output_type=str,
        system_prompt=SIMPLIFICA_SYSTEM_PROMPT,
        retries=3,
    )

    @agent.system_prompt
    def add_runtime_context(ctx: RunContext[AgentDeps]) -> str:
        d = ctx.deps
        when = d.current_datetime.strftime("%d/%m/%Y %H:%M") if d.current_datetime else "agora"
        lines = [
            f"Usuário: {d.user_name or 'profissional'}",
            f"Data/hora atual: {when} ({d.timezone})",
        ]
        if d.history_summary:
            lines.append(f"Resumo da conversa até aqui: {d.history_summary}")
        return "\n".join(lines)

    register_client_tools(agent)
    return agent
