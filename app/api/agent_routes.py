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
from app.services.event_service import EventService
from app.services.google_auth import has_credentials, load_credentials

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentMessageRequest(BaseModel):
    user_id: UUID
    message: str


class AgentMessageResponse(BaseModel):
    content: str


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()

    calendar_service = None
    if has_credentials(db, payload.user_id):
        try:
            from googleapiclient.discovery import build

            from app.services.google_calendar_service import GoogleCalendarService

            creds = load_credentials(db, payload.user_id)
            resource = build("calendar", "v3", credentials=creds, cache_discovery=False)
            calendar_service = GoogleCalendarService(resource, settings.TIMEZONE)
        except Exception:  # noqa: BLE001 - never 500 the chat on auth issues
            calendar_service = None

    deps = AgentDeps(
        db=db,
        user_id=payload.user_id,
        user_name=None,
        current_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
        timezone=settings.TIMEZONE,
        history_summary=None,
        client_service=ClientService(db),
        calendar_service=calendar_service,
        event_service=EventService(db),
    )
    result = await agent.run(payload.message, deps=deps)
    return AgentMessageResponse(content=result.output)
