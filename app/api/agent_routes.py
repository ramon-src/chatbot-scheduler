"""HTTP entrypoint for the SimplificaAgent."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.simplifica_agent import build_simplifica_agent
from app.core.database import get_db
from app.models.user import User
from app.services.agent_runner import (
    DEV_PHONE,
    build_agent_deps,
    process_professional_message,
)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageRequest(BaseModel):
    user_id: UUID
    message: str
    phone_number: str | None = None


class AgentMessageResponse(BaseModel):
    content: str


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()
    user = db.get(User, payload.user_id)

    # Unknown users get a one-shot answer (the chat_sessions FK needs a real user).
    if user is None:
        deps = build_agent_deps(
            db, User(id=payload.user_id, name="profissional", email=None), history_summary=None
        )
        result = await agent.run(payload.message, deps=deps)
        return AgentMessageResponse(content=result.output)

    reply = await process_professional_message(
        db, agent, user, payload.message, payload.phone_number or DEV_PHONE
    )
    return AgentMessageResponse(content=reply)
