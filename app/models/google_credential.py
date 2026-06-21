"""Per-user Google OAuth credentials (refresh token store)."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleCredential(Base):
    """OAuth2 credential for a user's Google Calendar (one per user)."""

    __tablename__ = "google_credentials"
    __table_args__ = {"schema": "simplificapsi"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simplificapsi.users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    refresh_token = Column(Text, nullable=False)
    token = Column(Text, nullable=True)
    token_uri = Column(String(255), nullable=False, default=DEFAULT_TOKEN_URI)
    client_id = Column(String(255), nullable=False)
    client_secret = Column(String(255), nullable=False)
    scopes = Column(Text, nullable=False)  # space-joined scope list
    expiry = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="google_credential")

    def __repr__(self) -> str:
        return f"<GoogleCredential(user_id={self.user_id})>"
