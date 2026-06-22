"""HTTP entrypoint for the SimplificaAgent."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.deps import AgentDeps
from app.agents.history import to_model_messages
from app.agents.simplifica_agent import build_simplifica_agent
from app.agents.summarizer import summarize_conversation
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.services.calendar_provider import build_calendar_access
from app.services.chat_history_service import ChatHistoryService
from app.services.client_service import ClientService
from app.services.event_service import EventService

logger = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# Most recent messages fed to the model verbatim; older ones live in the summary.
RAW_HISTORY_LIMIT = 10
# Fallback conversation channel for local/dev calls without a real WhatsApp number.
DEV_PHONE = "dev-cli"


class AgentMessageRequest(BaseModel):
    user_id: UUID
    message: str
    phone_number: str | None = None


class AgentMessageResponse(BaseModel):
    content: str


def _build_agent_deps(db: Session, user, history_summary: str | None = None) -> AgentDeps:
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
        history_summary=history_summary,
        client_service=ClientService(db),
        calendar_service=access.service if access else None,
        event_service=EventService(db),
    )


async def _maybe_update_summary(history: ChatHistoryService, session) -> None:
    """Fold any messages that fell out of the raw window into the rolling summary.

    Entirely best-effort: any failure (summary LLM call OR the surrounding DB
    queries/commit) is logged and swallowed, never breaking the already-computed
    chat response.
    """
    try:
        pending = history.unsummarized_overflow(session, keep_recent=RAW_HISTORY_LIMIT)
        if not pending:
            return
        new_summary = await summarize_conversation(session.summary, pending)
        history.fold_summary(session, new_summary, (session.summarized_count or 0) + len(pending))
    except Exception:  # noqa: BLE001 - summary is best-effort; never break the chat
        logger.warning("conversation summary update failed", exc_info=True)


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(payload: AgentMessageRequest, db: Session = Depends(get_db)):
    agent = build_simplifica_agent()
    user = db.get(User, payload.user_id)

    # Conversation memory only applies to a known user (the chat_sessions FK
    # requires a real users row). Unknown users still get a one-shot answer.
    if user is None:
        deps = _build_agent_deps(
            db, User(id=payload.user_id, name="profissional", email=None), history_summary=None
        )
        result = await agent.run(payload.message, deps=deps)
        return AgentMessageResponse(content=result.output)

    history = ChatHistoryService(db)
    session = history.get_or_create_session(payload.user_id, payload.phone_number or DEV_PHONE)
    message_history = to_model_messages(history.recent_messages(session, RAW_HISTORY_LIMIT))

    deps = _build_agent_deps(db, user, history_summary=session.summary)
    result = await agent.run(payload.message, deps=deps, message_history=message_history)

    history.append_turn(session, payload.message, result.output)
    await _maybe_update_summary(history, session)

    return AgentMessageResponse(content=result.output)
