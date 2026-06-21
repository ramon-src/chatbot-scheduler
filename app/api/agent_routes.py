"""HTTP entrypoint for the SimplificaAgent."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.deps import AgentDeps
from app.agents.simplifica_agent import build_simplifica_agent
from app.core.config import settings
from app.core.database import get_db
from app.services.client_service import ClientService

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageRequest(BaseModel):
    user_id: UUID
    message: str


class AgentMessageResponse(BaseModel):
    content: str


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()
    deps = AgentDeps(
        db=db,
        user_id=payload.user_id,
        user_name=None,
        current_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
        timezone=settings.TIMEZONE,
        history_summary=None,
        client_service=ClientService(db),
    )
    result = await agent.run(payload.message, deps=deps)
    return AgentMessageResponse(content=result.output)
