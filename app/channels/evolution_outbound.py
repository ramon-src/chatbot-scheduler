"""Evolution API outbound adapter: send a text message (best-effort)."""

from __future__ import annotations

import httpx

from app.channels.outbound import OutboundMessage
from app.core.logging import get_logger

logger = get_logger(__name__)


class EvolutionOutboundAdapter:
    provider = "evolution"

    def __init__(self, settings):
        self._url = settings.EVOLUTION_API_URL
        self._key = settings.EVOLUTION_API_KEY
        self._instance = settings.EVOLUTION_INSTANCE
        # DEV-ONLY: redirect every reply to this number (see config). None in prod.
        self._override = getattr(settings, "DEV_OUTBOUND_OVERRIDE_PHONE", None)

    def send(self, message: OutboundMessage) -> bool:
        if not (self._url and self._key and self._instance):
            logger.warning("evolution outbound not configured — dropping reply")
            return False
        number = self._override or message.to_phone
        if self._override:
            logger.warning("DEV outbound override: redirecting reply to %s", self._override)
        try:
            resp = httpx.post(
                f"{self._url}/message/sendText/{self._instance}",
                headers={"apikey": self._key},
                json={"number": number, "text": message.text},
                timeout=10,
            )
            return resp.status_code < 400
        except Exception:  # noqa: BLE001 - outbound is best-effort, never raise
            logger.warning("evolution outbound send failed", exc_info=True)
            return False
