"""LeadAgent: sales/onboarding agent for unknown WhatsApp numbers (prospects)."""

from pydantic_ai import Agent, RunContext

from app.agents.deps import LeadAgentDeps
from app.agents.foundation import get_llm_model
from app.agents.knowledge.product_faq import PRODUCT_SUMMARY
from app.agents.tools.lead_tools import register_lead_tools
from app.core.config import settings

LEAD_SYSTEM_PROMPT = f"""Você é o assistente de vendas do Simplifica Psi, falando no WhatsApp com
um possível novo cliente (um psicólogo ou terapeuta que ainda NÃO tem conta).

OBJETIVO:
- Apresentar o produto de forma acolhedora e objetiva, tirar dúvidas e conduzir a pessoa ao cadastro.
- Quando a pessoa demonstrar interesse em começar, colete o nome completo e um e-mail e crie a conta
  de teste usando a tool. NÃO invente conta sem nome e e-mail.

SOBRE O PRODUTO:
{PRODUCT_SUMMARY}

REGRAS DE RESPOSTA:
- Responda sempre em Português do Brasil, tom simpático e direto, mensagens curtas (é WhatsApp).
- NUNCA exponha IDs, códigos, JSON, links ou termos técnicos.
- Use as tools para salvar dados do interessado, responder dúvidas e criar a conta. Nunca invente dados.
- O período de teste é gratuito; o link de pagamento é enviado depois (não prometa nada além disso).
- Se a pessoa claramente já é cliente ou quer falar de uma conta existente, oriente que ela use o
  número já cadastrado.
"""


def build_lead_agent() -> Agent[LeadAgentDeps, str]:
    agent = Agent(
        get_llm_model(settings.LEAD_AGENT_MODEL, temperature=0.2, timeout=30),
        deps_type=LeadAgentDeps,
        output_type=str,
        system_prompt=LEAD_SYSTEM_PROMPT,
        retries=3,
    )

    @agent.system_prompt
    def add_runtime_context(ctx: RunContext[LeadAgentDeps]) -> str:
        d = ctx.deps
        when = d.current_datetime.strftime("%d/%m/%Y %H:%M") if d.current_datetime else "agora"
        lines = [
            f"Interessado: {d.lead_name or 'ainda sem nome'}",
            f"Data/hora atual: {when} ({d.timezone})",
        ]
        if d.history_summary:
            lines.append(f"Resumo da conversa até aqui: {d.history_summary}")
        return "\n".join(lines)

    register_lead_tools(agent)
    return agent
