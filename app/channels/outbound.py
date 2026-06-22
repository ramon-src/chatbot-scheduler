"""Provider-agnostic outbound message port (send a reply back to the user)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class OutboundMessage:
    to_phone: str  # normalized recipient
    text: str


@runtime_checkable
class OutboundAdapter(Protocol):
    provider: str

    def send(self, message: OutboundMessage) -> bool:
        """Best-effort send. Returns True if accepted, False otherwise. Never raises."""
        ...
