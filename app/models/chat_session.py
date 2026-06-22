"""
Chat session model for SQLAlchemy
"""

import uuid

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ChatSession(Base):
    """Chat session model"""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL) <> (lead_id IS NOT NULL)",
            name="ck_chat_sessions_one_owner",
        ),
        {"schema": "simplificapsi"},
    )

    # =============================================================================
    # PRIMARY KEY
    # =============================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # =============================================================================
    # FOREIGN KEYS
    # =============================================================================
    user_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.users.id", ondelete="CASCADE"), nullable=True, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.leads.id", ondelete="CASCADE"), nullable=True, index=True)

    # =============================================================================
    # BASIC INFO
    # =============================================================================
    session_id = Column(String(255), nullable=False, index=True)
    phone_number = Column(String(20), nullable=True, index=True)

    # Rolling summary of older messages folded out of the raw window
    summary = Column(Text, nullable=True)
    # How many messages have already been folded into `summary`
    summarized_count = Column(Integer, nullable=False, server_default="0", default=0)

    # =============================================================================
    # STATUS
    # =============================================================================
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # =============================================================================
    # TIMESTAMPS
    # =============================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # =============================================================================
    # RELATIONSHIPS
    # =============================================================================
    user = relationship("User", back_populates="chat_sessions")
    lead = relationship("Lead", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

    # =============================================================================
    # METHODS
    # =============================================================================
    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, session_id={self.session_id}, phone={self.phone_number})>"

    def __str__(self) -> str:
        return f"Session {self.session_id} ({self.phone_number or 'No phone'})"

    @property
    def message_count(self) -> int:
        """Get total number of messages in this session"""
        return len(self.messages) if self.messages else 0

    @property
    def last_message_time(self) -> str:
        """Get timestamp of last message"""
        if not self.messages:
            return None

        last_message = max(self.messages, key=lambda m: m.created_at)
        return last_message.created_at.isoformat() if last_message.created_at else None

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "session_id": self.session_id,
            "phone_number": self.phone_number,
            "is_active": self.is_active,
            "message_count": self.message_count,
            "last_message_time": self.last_message_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class ChatMessage(Base):
    """Chat message model"""

    __tablename__ = "chat_messages"
    __table_args__ = {"schema": "simplificapsi"}

    # =============================================================================
    # PRIMARY KEY
    # =============================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # =============================================================================
    # FOREIGN KEYS
    # =============================================================================
    session_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    # =============================================================================
    # BASIC INFO
    # =============================================================================
    message_type = Column(String(50), nullable=False, index=True)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    # DB column is named "metadata" (migration 0001); the attribute can't be
    # "metadata" because SQLAlchemy reserves it on the declarative base.
    message_metadata = Column("metadata", JSON, nullable=True)

    # =============================================================================
    # TIMESTAMPS
    # =============================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # =============================================================================
    # RELATIONSHIPS
    # =============================================================================
    session = relationship("ChatSession", back_populates="messages")

    # =============================================================================
    # METHODS
    # =============================================================================
    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, type={self.message_type}, content={self.content[:50]}...)>"

    def __str__(self) -> str:
        return f"{self.message_type}: {self.content[:100]}{'...' if len(self.content) > 100 else ''}"

    @property
    def is_user_message(self) -> bool:
        """Check if this is a user message"""
        return self.message_type == "user"

    @property
    def is_assistant_message(self) -> bool:
        """Check if this is an assistant message"""
        return self.message_type == "assistant"

    @property
    def is_system_message(self) -> bool:
        """Check if this is a system message"""
        return self.message_type == "system"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "message_type": self.message_type,
            "content": self.content,
            "message_metadata": self.message_metadata,
            "is_user_message": self.is_user_message,
            "is_assistant_message": self.is_assistant_message,
            "is_system_message": self.is_system_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

