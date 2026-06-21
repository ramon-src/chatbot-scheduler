"""Typed dependencies injected into the SimplificaAgent run."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.client_service import ClientService


@dataclass
class AgentDeps:
    db: Session
    user_id: UUID
    user_name: Optional[str]
    current_datetime: datetime
    timezone: str
    history_summary: Optional[str]
    client_service: ClientService
