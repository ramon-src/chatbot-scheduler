"""Reusable professional-agent processing core.

Shared by the HTTP /agent/message route and the WhatsApp webhook ingestion so
both drive the exact same memory flow (replay -> run -> persist -> fold).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agents.deps import AgentDeps
from app.agents.history import to_model_messages
from app.agents.summarizer import summarize_conversation
from app.core.config import settings
from app.core.logging import get_logger
from app.services.calendar_provider import build_calendar_access
from app.services.chat_history_service import ChatHistoryService
from app.services.client_service import ClientService
from app.services.event_service import EventService

logger = get_logger(__name__)

# Most recent messages fed to the model verbatim; older ones live in the summary.
RAW_HISTORY_LIMIT = 10
# Fallback conversation channel for local/dev calls without a real WhatsApp number.
DEV_PHONE = "dev-cli"


def build_agent_deps(db: Session, user, history_summary: str | None = None) -> AgentDeps:
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


def _persist_turn(db, history, session, user_text, assistant_text) -> bool:
    try:
        history.append_turn(session, user_text, assistant_text)
        return True
    except Exception:  # noqa: BLE001 - never lose the answer after it is computed
        logger.warning("failed to persist conversation turn", exc_info=True)
        db.rollback()
        return False


async def _maybe_update_summary(history: ChatHistoryService, session) -> None:
    try:
        pending = history.unsummarized_overflow(session, keep_recent=RAW_HISTORY_LIMIT)
        if not pending:
            return
        new_summary = await summarize_conversation(session.summary, pending)
        history.fold_summary(session, new_summary, (session.summarized_count or 0) + len(pending))
    except Exception:  # noqa: BLE001 - summary is best-effort; never break the chat
        logger.warning("conversation summary update failed", exc_info=True)


async def process_professional_message(db: Session, agent, user, text: str, phone: str) -> str:
    """Run the full memory flow for a known professional and return the reply text."""
    history = ChatHistoryService(db)
    session = history.get_or_create_session(user.id, phone or DEV_PHONE)
    message_history = to_model_messages(history.recent_messages(session, RAW_HISTORY_LIMIT))

    deps = build_agent_deps(db, user, history_summary=session.summary)
    result = await agent.run(text, deps=deps, message_history=message_history)

    if _persist_turn(db, history, session, text, result.output):
        await _maybe_update_summary(history, session)
    return result.output
