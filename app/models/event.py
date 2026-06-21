"""
Event model for SQLAlchemy
"""

from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from enum import Enum

from app.core.database import Base

class EventStatus(str, Enum):
    """Event status enumeration"""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"

class PaymentStatus(str, Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

class Event(Base):
    """Event model"""
    
    __tablename__ = "events"
    __table_args__ = {"schema": "simplificapsi"}
    
    # =============================================================================
    # PRIMARY KEY
    # =============================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # =============================================================================
    # FOREIGN KEYS
    # =============================================================================
    user_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.clients.id", ondelete="SET NULL"), nullable=True, index=True)
    calendar_id = Column(UUID(as_uuid=True), ForeignKey("simplificapsi.calendars.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # =============================================================================
    # BASIC INFO
    # =============================================================================
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # =============================================================================
    # RECURRENCE
    # =============================================================================
    is_recurring = Column(Boolean, default=False, nullable=False, index=True)
    recurrence_rule = Column(String(255), nullable=True)
    
    # =============================================================================
    # EXTERNAL INTEGRATION
    # =============================================================================
    google_event_id = Column(String(255), nullable=True, unique=True, index=True)
    
    # =============================================================================
    # STATUS
    # =============================================================================
    status = Column(String(50), default=EventStatus.SCHEDULED, nullable=False, index=True)
    payment_status = Column(String(50), default=PaymentStatus.PENDING, nullable=False, index=True)
    
    # =============================================================================
    # FINANCIAL
    # =============================================================================
    price = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)
    
    # =============================================================================
    # TIMESTAMPS
    # =============================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # =============================================================================
    # RELATIONSHIPS
    # =============================================================================
    user = relationship("User", back_populates="events")
    client = relationship("Client", back_populates="events")
    calendar = relationship("Calendar", back_populates="events")
    
    # =============================================================================
    # METHODS
    # =============================================================================
    def __repr__(self) -> str:
        return f"<Event(id={self.id}, title={self.title}, start_time={self.start_time})>"
    
    def __str__(self) -> str:
        return f"{self.title} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"
    
    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes"""
        if not self.start_time or not self.end_time:
            return 0
        return int((self.end_time - self.start_time).total_seconds() / 60)
    
    @property
    def duration_hours(self) -> float:
        """Calculate event duration in hours"""
        return self.duration_minutes / 60
    
    @property
    def is_past(self) -> bool:
        """Check if event is in the past"""
        from datetime import datetime
        return self.end_time < datetime.now(self.end_time.tzinfo)
    
    @property
    def is_upcoming(self) -> bool:
        """Check if event is upcoming"""
        from datetime import datetime
        return self.start_time > datetime.now(self.start_time.tzinfo)
    
    @property
    def is_current(self) -> bool:
        """Check if event is currently happening"""
        from datetime import datetime
        now = datetime.now(self.start_time.tzinfo)
        return self.start_time <= now <= self.end_time
    
    @property
    def client_name(self) -> str:
        """Get client name or 'No client'"""
        return self.client.name if self.client else "No client"
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "client_id": str(self.client_id) if self.client_id else None,
            "calendar_id": str(self.calendar_id),
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_minutes": self.duration_minutes,
            "duration_hours": self.duration_hours,
            "is_recurring": self.is_recurring,
            "recurrence_rule": self.recurrence_rule,
            "google_event_id": self.google_event_id,
            "status": self.status,
            "payment_status": self.payment_status,
            "price": float(self.price) if self.price else None,
            "notes": self.notes,
            "client_name": self.client_name,
            "is_past": self.is_past,
            "is_upcoming": self.is_upcoming,
            "is_current": self.is_current,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

