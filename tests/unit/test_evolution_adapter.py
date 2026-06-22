import datetime

from app.channels.evolution_adapter import EvolutionInboundAdapter


def _payload(**over):
    base = {
        "event": "messages.upsert",
        "instance": "psi",
        "data": {
            "key": {"remoteJid": "5551999998888@s.whatsapp.net", "fromMe": False, "id": "EVT1"},
            "message": {"conversation": "quero marcar uma sessão"},
            "messageTimestamp": 1718900000,
            "pushName": "Fulano",
        },
    }
    base.update(over)
    return base


def test_parses_conversation_message():
    msg = EvolutionInboundAdapter().parse(_payload())
    assert msg is not None
    assert msg.provider == "evolution"
    assert msg.sender_phone == "5551999998888"
    assert msg.text == "quero marcar uma sessão"
    assert msg.provider_message_id == "EVT1"
    assert msg.timestamp.tzinfo == datetime.UTC
    assert msg.raw["event"] == "messages.upsert"


def test_parses_extended_text_message():
    p = _payload()
    p["data"]["message"] = {"extendedTextMessage": {"text": "olá de novo"}}
    msg = EvolutionInboundAdapter().parse(p)
    assert msg is not None and msg.text == "olá de novo"


def test_ignores_from_me_echo():
    p = _payload()
    p["data"]["key"]["fromMe"] = True
    assert EvolutionInboundAdapter().parse(p) is None


def test_ignores_non_message_event():
    assert EvolutionInboundAdapter().parse({"event": "messages.update", "data": {}}) is None


def test_ignores_message_without_text():
    p = _payload()
    p["data"]["message"] = {"imageMessage": {"url": "x"}}
    assert EvolutionInboundAdapter().parse(p) is None
