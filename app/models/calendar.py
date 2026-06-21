"""
Calendar model for SQLAlchemy
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base

class Calendar(Base):
    """Calendar model"""

    __tablename__ = "calendars"
    # google_calendar_id (e.g. the literal "primary") is unique PER USER, not
    # globally — every user's own primary calendar is identified as "primary".
    __table_args__ = (
        UniqueConstraint("user_id", "google_calendar_id", name="uq_calendars_user_google_id"),
        {"schema": "simplificapsi"},
    )
    
    # =============================================================================
    # PRIMARY KEY
    # =============================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # =============================================================================
    # FOREIGN KEYS
    # =============================================================================
    user_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # =============================================================================
    # BASIC INFO
    # =============================================================================
    name = Column(String(255), nullable=False)
    google_calendar_id = Column(String(255), nullable=True, index=True)
    
    # =============================================================================
    # STATUS
    # =============================================================================
    is_primary = Column(Boolean, default=False, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # =============================================================================
    # TIMESTAMPS
    # =============================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # =============================================================================
    # RELATIONSHIPS
    # =============================================================================
    user = relationship("User", back_populates="calendars")
    events = relationship("Event", back_populates="calendar", cascade="all, delete-orphan")
    
    # =============================================================================
    # METHODS
    # =============================================================================
    def __repr__(self) -> str:
        return f"<Calendar(id={self.id}, name={self.name}, is_primary={self.is_primary})>"
    
    def __str__(self) -> str:
        return f"{self.name} {'(Primary)' if self.is_primary else ''}"
    
    @property
    def is_google_calendar(self) -> bool:
        """Check if this is a Google Calendar"""
        return self.google_calendar_id is not None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "google_calendar_id": self.google_calendar_id,
            "is_primary": self.is_primary,
            "is_active": self.is_active,
            "is_google_calendar": self.is_google_calendar,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

