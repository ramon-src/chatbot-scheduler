"""
User model for SQLAlchemy
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func

from app.channels.phone import normalize_phone
from app.core.database import Base


class User(Base):
    """User model"""

    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_phone_normalized", "phone_normalized", unique=True),
        {"schema": "simplificapsi"},
    )

    # =============================================================================
    # PRIMARY KEY
    # =============================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # =============================================================================
    # BASIC INFO
    # =============================================================================
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    phone_normalized = Column(String(20), nullable=True)
    name = Column(String(255), nullable=False)

    # =============================================================================
    # STATUS
    # =============================================================================
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # =============================================================================
    # TIMESTAMPS
    # =============================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    # Trial expiry for accounts created by the lead agent (NULL = no expiry).
    access_expires_at = Column(DateTime(timezone=True), nullable=True)

    # =============================================================================
    # RELATIONSHIPS
    # =============================================================================
    clients = relationship("Client", back_populates="user", cascade="all, delete-orphan")
    calendars = relationship("Calendar", back_populates="user", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    google_credential = relationship(
        "GoogleCredential", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    # =============================================================================
    # METHODS
    # =============================================================================
    @validates("phone")
    def _derive_phone_normalized(self, key, value):
        """Keep phone_normalized in sync with phone on every write (the
        registration-time enforcement point for the uniqueness constraint)."""
        self.phone_normalized = normalize_phone(value) or None
        return value

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, name={self.name})>"

    def __str__(self) -> str:
        return f"{self.name} ({self.email})"

    @property
    def is_psychologist(self) -> bool:
        """Check if user is a psychologist"""
        return True  # All users in this system are psychologists

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "email": self.email,
            "phone": self.phone,
            "name": self.name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

