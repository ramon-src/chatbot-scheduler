"""Provider-agnostic inbound message port.

Every WhatsApp provider has an adapter that translates its raw webhook payload
into a single `InboundMessage`. The agent never sees `provider` — only the
ingestion layer uses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class InboundMessage:
    provider: str
    sender_phone: str
    text: str
    provider_message_id: str
    timestamp: datetime
    recipient_phone: str | None
    raw: dict


@runtime_checkable
class InboundAdapter(Protocol):
    provider: str

    def parse(self, payload: dict) -> InboundMessage | None:
        """Translate a raw provider webhook payload into an InboundMessage.

        Returns None for non-message events (delivery/read statuses, presence,
        echoes of our own outbound messages, etc.).
        """
        ...
