"""Help/FAQ tool for the professional agent (how to use Simplifica Psi)."""

from app.agents.deps import AgentDeps
from app.agents.knowledge.product_faq import lookup


def register_help_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def product_help(ctx: RunContext[AgentDeps], topic: str | None = None) -> dict:
        """Explica como usar o Simplifica Psi (cadastro de clientes, agenda, cobrança)."""
        return {"success": True, "data": None, "message": lookup(topic)}
