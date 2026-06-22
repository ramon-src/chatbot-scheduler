import hashlib
import hmac

from app.channels.meta_adapter import (
    MetaInboundAdapter,
    valid_meta_signature,
    verify_meta_handshake,
)


def _msg_payload():
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"display_phone_number": "5551888887777"},
                            "messages": [
                                {
                                    "from": "5551999998888",
                                    "id": "wamid.ABC",
                                    "timestamp": "1718900000",
                                    "type": "text",
                                    "text": {"body": "olá pelo meta"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def test_parses_meta_text_message():
    msg = MetaInboundAdapter().parse(_msg_payload())
    assert msg is not None
    assert msg.provider == "meta"
    assert msg.sender_phone == "5551999998888"
    assert msg.text == "olá pelo meta"
    assert msg.provider_message_id == "wamid.ABC"
    assert msg.recipient_phone == "5551888887777"


def test_ignores_status_only_payload():
    payload = {"object": "whatsapp_business_account",
               "entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert MetaInboundAdapter().parse(payload) is None


def test_handshake_returns_challenge_on_valid_token():
    assert verify_meta_handshake("subscribe", "tok", "ch123", "tok") == "ch123"


def test_handshake_rejects_bad_token():
    assert verify_meta_handshake("subscribe", "wrong", "ch123", "tok") is None


def test_signature_disabled_when_no_secret():
    assert valid_meta_signature(b"{}", None, None) is True


def test_signature_matches():
    body = b'{"a":1}'
    secret = "shh"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert valid_meta_signature(body, f"sha256={digest}", secret) is True
    assert valid_meta_signature(body, "sha256=deadbeef", secret) is False
