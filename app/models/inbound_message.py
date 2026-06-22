"""Inbound WhatsApp message record: idempotency + audit + lead queue."""

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.core.database import Base


class InboundMessageRecord(Base):
    """One received WhatsApp message, regardless of provider.

    `classification` is "professional" when `sender_phone` matched a User, else
    "lead". Lead rows are the queue a future client-facing agent will consume.
    """

    __tablename__ = "inbound_message"
    __table_args__ = (
        UniqueConstraint("provider", "provider_message_id", name="uq_inbound_provider_msg"),
        {"schema": "simplificapsi"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    provider_message_id = Column(String(255), nullable=False)
    sender_phone = Column(String(20), nullable=False, index=True)
    recipient_phone = Column(String(20), nullable=True)
    text = Column(Text, nullable=False)
    classification = Column(String(20), nullable=False, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simplificapsi.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw = Column(JSONB, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<InboundMessageRecord(provider={self.provider}, "
            f"msg_id={self.provider_message_id}, class={self.classification})>"
        )
