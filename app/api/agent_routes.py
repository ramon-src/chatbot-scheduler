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
from app.models.user import User
from app.services.calendar_provider import build_calendar_access
from app.services.client_service import ClientService
from app.services.event_service import EventService

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageRequest(BaseModel):
    user_id: UUID
    message: str


class AgentMessageResponse(BaseModel):
    content: str


def _build_agent_deps(db: Session, user) -> AgentDeps:
    access = None
    try:
        access = build_calendar_access(db, user, settings)
    except Exception:  # noqa: BLE001 - never 500 the chat on calendar setup
        access = None
    return AgentDeps(
        db=db,
        user_id=user.id,
        user_name=user.name,
        current_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
        timezone=settings.TIMEZONE,
        history_summary=None,
        client_service=ClientService(db),
        calendar_service=access.service if access else None,
        event_service=EventService(db),
    )


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()
    user = db.get(User, payload.user_id)
    if user is None:
        # unknown user: run with no calendar/user context (client tools still scope by user_id)
        user = User(id=payload.user_id, name="profissional", email=None)
    deps = _build_agent_deps(db, user)
    result = await agent.run(payload.message, deps=deps)
    return AgentMessageResponse(content=result.output)
