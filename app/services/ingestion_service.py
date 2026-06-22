"""Ingestion orchestrator: idempotency -> classify -> route.

`handle` is synchronous and deterministic (no LLM): it dedupes, resolves the
sender, and records the message. The slow agent run for professionals is run
separately via `dispatch_agent_run` (scheduled on FastAPI BackgroundTasks).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Imported at module scope so tests can monkeypatch it.
from app.agents.simplifica_agent import build_simplifica_agent
from app.channels.inbound import InboundMessage
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.inbound_message import InboundMessageRecord
from app.models.user import User
from app.services.agent_runner import process_professional_message
from app.services.calendar_provider import (
    build_calendar_access,  # noqa: F401 (patch target for tests)
)
from app.services.identity_service import resolve_sender

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    status: str  # "duplicate" | "professional" | "lead"
    user_id: UUID | None
    record_id: UUID | None


class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    def handle(self, inbound: InboundMessage) -> IngestionResult:
        user = resolve_sender(self.db, inbound.sender_phone)
        classification = "professional" if user is not None else "lead"
        record = InboundMessageRecord(
            provider=inbound.provider,
            provider_message_id=inbound.provider_message_id,
            sender_phone=inbound.sender_phone,
            recipient_phone=inbound.recipient_phone,
            text=inbound.text,
            classification=classification,
            user_id=user.id if user is not None else None,
            raw=inbound.raw,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            # Unique (provider, provider_message_id) violated -> redelivery.
            self.db.rollback()
            return IngestionResult(status="duplicate", user_id=None, record_id=None)
        self.db.refresh(record)
        return IngestionResult(
            status=classification,
            user_id=user.id if user is not None else None,
            record_id=record.id,
        )


async def dispatch_agent_run(inbound: InboundMessage, user_id: UUID) -> None:
    """Run the professional agent for an already-recorded message.

    Opens its own DB session (it runs after the webhook response, on a
    BackgroundTask). Best-effort: logs and swallows any failure.
    """
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        agent = build_simplifica_agent()
        await process_professional_message(db, agent, user, inbound.text, inbound.sender_phone)
    except Exception:  # noqa: BLE001 - background work must never raise
        logger.warning("agent run for inbound message failed", exc_info=True)
    finally:
        db.close()
