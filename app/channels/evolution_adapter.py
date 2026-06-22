"""Evolution API inbound adapter: raw webhook payload -> InboundMessage."""

from __future__ import annotations

import datetime as _dt
from datetime import datetime

from app.channels.inbound import InboundMessage
from app.channels.phone import normalize_phone


def _extract_text(message: dict) -> str | None:
    if not isinstance(message, dict):
        return None
    conversation = message.get("conversation")
    if isinstance(conversation, str) and conversation:
        return conversation
    extended = message.get("extendedTextMessage")
    if isinstance(extended, dict):
        text = extended.get("text")
        if isinstance(text, str) and text:
            return text
    return None


class EvolutionInboundAdapter:
    provider = "evolution"

    def parse(self, payload: dict) -> InboundMessage | None:
        if payload.get("event") != "messages.upsert":
            return None
        data = payload.get("data") or {}
        key = data.get("key") or {}
        if key.get("fromMe"):
            return None
        text = _extract_text(data.get("message") or {})
        if text is None:
            return None
        remote_jid = key.get("remoteJid") or ""
        message_id = key.get("id") or ""
        ts_raw = data.get("messageTimestamp")
        try:
            timestamp = datetime.fromtimestamp(int(ts_raw), tz=_dt.UTC)
        except (TypeError, ValueError):
            timestamp = datetime.now(tz=_dt.UTC)
        return InboundMessage(
            provider=self.provider,
            sender_phone=normalize_phone(remote_jid),
            text=text,
            provider_message_id=message_id,
            timestamp=timestamp,
            recipient_phone=None,
            raw=payload,
        )
