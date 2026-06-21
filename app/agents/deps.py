"""Typed dependencies injected into the SimplificaAgent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.client_service import ClientService

if TYPE_CHECKING:
    from app.services.event_service import EventService
    from app.services.google_calendar_service import GoogleCalendarService


@dataclass
class AgentDeps:
    db: Session
    user_id: UUID
    user_name: Optional[str]
    current_datetime: datetime
    timezone: str
    history_summary: Optional[str]
    client_service: ClientService
    calendar_service: Optional["GoogleCalendarService"] = field(default=None)
    event_service: Optional["EventService"] = field(default=None)
    default_consult_minutes: int = 60
