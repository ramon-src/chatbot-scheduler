"""
Client model for SQLAlchemy
"""

from enum import Enum

from sqlalchemy import Column, String, Boolean, DateTime, Text, Date, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class BillingMode(str, Enum):
    """How a client is billed."""
    PER_SESSION = "per_session"
    MONTHLY = "monthly"

class Client(Base):
    """Client model"""
    
    __tablename__ = "clients"
    __table_args__ = {"schema": "simplificapsi"}
    
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
    name = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    birth_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    invoice_day = Column(Integer, nullable=True)  # nullable at DB level for legacy/other write paths; ClientCreate requires it on create
    consult_price = Column(Numeric(10, 2), nullable=True)  # nullable at DB level for legacy/other write paths; ClientCreate requires it on create
    billing_mode = Column(String(20), nullable=False, server_default="monthly")

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
    user = relationship("User", back_populates="clients")
    events = relationship("Event", back_populates="client", cascade="all, delete-orphan")
    
    # =============================================================================
    # METHODS
    # =============================================================================
    def __repr__(self) -> str:
        return f"<Client(id={self.id}, name={self.name}, phone={self.phone})>"
    
    def __str__(self) -> str:
        return f"{self.name} ({self.phone or self.email or 'No contact'})"
    
    @property
    def age(self) -> int:
        """Calculate client age"""
        if not self.birth_date:
            return None
        
        from datetime import date
        today = date.today()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
    
    @property
    def contact_info(self) -> str:
        """Get primary contact information"""
        if self.phone:
            return self.phone
        elif self.email:
            return self.email
        return "No contact information"
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "age": self.age,
            "notes": self.notes,
            "is_active": self.is_active,
            "contact_info": self.contact_info,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

