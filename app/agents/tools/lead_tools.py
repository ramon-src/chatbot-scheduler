"""Lead agent tools: pure impls + thin @agent.tool wrappers."""

from app.agents.deps import LeadAgentDeps
from app.agents.knowledge.product_faq import lookup
from app.core.exceptions import ConflictError

_VALID_STATUS = {"new", "engaged", "qualified", "converted"}


async def update_lead_info_impl(
    deps: LeadAgentDeps, name=None, email=None, notes=None, status=None
) -> dict:
    lead = deps.lead_service.get_lead(deps.lead_id)
    if lead is None:
        return {"success": False, "data": None, "message": "Não consegui localizar seu cadastro."}
    if status is not None and status not in _VALID_STATUS:
        status = None
    deps.lead_service.update_lead(lead, name=name, email=email, notes=notes, status=status)
    return {"success": True, "data": {"name": lead.name}, "message": "Anotado!"}


async def create_professional_account_impl(deps: LeadAgentDeps, name=None, email=None) -> dict:
    if not name or not email:
        return {
            "success": False, "data": None,
            "message": "Para criar sua conta eu preciso do seu nome completo e de um e-mail.",
        }
    lead = deps.lead_service.get_lead(deps.lead_id)
    if lead is None:
        return {"success": False, "data": None, "message": "Não consegui localizar seu cadastro."}
    try:
        user, created = deps.lead_service.convert_to_account(lead, name, email, deps.trial_days)
    except ConflictError as exc:
        return {"success": False, "data": None, "message": str(exc)}

    first = (user.name or name).split()[0]
    if not created:
        return {
            "success": True, "data": {"name": user.name},
            "message": f"{first}, você já tem uma conta com a gente. É só me chamar que eu te ajudo.",
        }
    return {
        "success": True, "data": {"name": user.name},
        "message": (
            f"Pronto, {first}! Criei sua conta de teste, válida por {deps.trial_days} dias. "
            f"Daqui a pouco te envio o link de pagamento para ativar de vez."
        ),
    }


def register_lead_tools(agent) -> None:
    from pydantic_ai import RunContext

    @agent.tool
    async def update_lead_info(
        ctx: RunContext[LeadAgentDeps],
        name: str | None = None, email: str | None = None,
        notes: str | None = None, status: str | None = None,
    ) -> dict:
        """Salva nome/e-mail/observações do interessado e atualiza o estágio do lead."""
        return await update_lead_info_impl(ctx.deps, name, email, notes, status)

    @agent.tool
    async def create_professional_account(
        ctx: RunContext[LeadAgentDeps], name: str, email: str
    ) -> dict:
        """Cria a conta de teste do profissional (precisa de nome completo e e-mail)."""
        return await create_professional_account_impl(ctx.deps, name, email)

    @agent.tool
    async def product_faq(ctx: RunContext[LeadAgentDeps], topic: str | None = None) -> dict:
        """Responde dúvidas sobre o Simplifica Psi (o que faz, preço, como começar)."""
        return {"success": True, "data": None, "message": lookup(topic)}
