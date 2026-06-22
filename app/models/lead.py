"""Lead model: an unknown WhatsApp number being qualified by the lead agent."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Lead(Base):
    """A prospective professional (unlinked sender) in the qualification funnel."""

    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("phone", name="uq_leads_phone"),
        {"schema": "simplificapsi"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    # new | engaged | qualified | converted
    status = Column(String(20), nullable=False, server_default="new", default="new", index=True)
    notes = Column(Text, nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simplificapsi.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # chat_sessions relationship is wired in Task 3 once lead_id FK is added to
    # chat_sessions and back_populates="lead" is set on the ChatSession side.

    def __repr__(self) -> str:
        return f"<Lead(id={self.id}, phone={self.phone}, status={self.status})>"
