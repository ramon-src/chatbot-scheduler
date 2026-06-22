"""Meta Cloud API inbound adapter (scaffold) + webhook verification helpers.

Secondary provider behind the same port as Evolution. Implemented enough to
parse a text message and verify the webhook; not the default channel.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac

from app.channels.inbound import InboundMessage
from app.channels.phone import normalize_phone


class MetaInboundAdapter:
    provider = "meta"

    def parse(self, payload: dict) -> InboundMessage | None:
        try:
            change = payload["entry"][0]["changes"][0]["value"]
        except (KeyError, IndexError, TypeError):
            return None
        messages = change.get("messages")
        if not messages:
            return None
        message = messages[0]
        if message.get("type") != "text":
            return None
        body = (message.get("text") or {}).get("body")
        if not body:
            return None
        ts_raw = message.get("timestamp")
        try:
            timestamp = datetime.datetime.fromtimestamp(int(ts_raw), tz=datetime.UTC)
        except (TypeError, ValueError):
            timestamp = datetime.datetime.now(tz=datetime.UTC)
        recipient = (change.get("metadata") or {}).get("display_phone_number")
        return InboundMessage(
            provider=self.provider,
            sender_phone=normalize_phone(message.get("from")),
            text=body,
            provider_message_id=message.get("id") or "",
            timestamp=timestamp,
            recipient_phone=normalize_phone(recipient) or None,
            raw=payload,
        )


def verify_meta_handshake(
    mode: str | None, token: str | None, challenge: str | None, expected_token: str
) -> str | None:
    if mode == "subscribe" and token and token == expected_token:
        return challenge
    return None


def valid_meta_signature(raw_body: bytes, header: str | None, app_secret: str | None) -> bool:
    if not app_secret:
        return True  # signature verification disabled (dev)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])
