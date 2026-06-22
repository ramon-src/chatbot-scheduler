from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.channels.inbound import InboundMessage


def test_inbound_message_is_frozen_and_holds_fields():
    msg = InboundMessage(
        provider="evolution",
        sender_phone="5551999998888",
        text="olá",
        provider_message_id="ABC123",
        timestamp=datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        recipient_phone="5551888887777",
        raw={"k": "v"},
    )
    assert msg.provider == "evolution"
    assert msg.sender_phone == "5551999998888"
    assert msg.text == "olá"
    assert msg.provider_message_id == "ABC123"
    assert msg.recipient_phone == "5551888887777"
    assert msg.raw == {"k": "v"}
    with pytest.raises(FrozenInstanceError):
        msg.text = "mutado"  # type: ignore[misc]
