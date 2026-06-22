# tests/integration/test_webhook_routes.py
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.inbound_message import InboundMessageRecord
from app.models.user import User

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
PRO_PHONE = "+5551955554444"


def _evolution_payload(message_id, remote_jid, text="quero marcar"):
    return {
        "event": "messages.upsert",
        "instance": "psi",
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": False, "id": message_id},
            "message": {"conversation": text},
            "messageTimestamp": 1718900000,
            "pushName": "Fulano",
        },
    }


def _purge(message_id):
    db = SessionLocal()
    try:
        db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == message_id
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_meta_handshake_returns_challenge(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verifytok")
    client = TestClient(app)
    r = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "verifytok", "hub.challenge": "42"},
    )
    assert r.status_code == 200
    assert r.text.strip('"') == "42"


def test_meta_handshake_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verifytok")
    client = TestClient(app)
    r = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "WRONG", "hub.challenge": "42"},
    )
    assert r.status_code == 403


def test_evolution_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", "evotok")
    client = TestClient(app)
    r = client.post(
        "/webhooks/evolution",
        json=_evolution_payload("WH-BAD", "5551911110000@s.whatsapp.net"),
        headers={"X-Webhook-Token": "WRONG"},
    )
    assert r.status_code == 403


def test_evolution_unknown_number_parks_lead(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)  # token check disabled
    client = TestClient(app)
    try:
        r = client.post(
            "/webhooks/evolution",
            json=_evolution_payload("WH-LEAD", "5551911110000@s.whatsapp.net"),
        )
        assert r.status_code == 200
        db = SessionLocal()
        try:
            rec = db.query(InboundMessageRecord).filter(
                InboundMessageRecord.provider_message_id == "WH-LEAD"
            ).one()
            assert rec.classification == "lead"
        finally:
            db.close()
    finally:
        _purge("WH-LEAD")


def test_evolution_known_professional_schedules_agent(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    # point dev user's phone at PRO_PHONE so it resolves
    setup = SessionLocal()
    user = setup.get(User, DEV_USER_ID)
    previous = user.phone
    user.phone = PRO_PHONE
    setup.commit()
    setup.close()

    scheduled = {}

    async def fake_dispatch(inbound, user_id):
        scheduled["user_id"] = user_id
        scheduled["text"] = inbound.text

    # TestClient runs BackgroundTasks synchronously after the response.
    with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
        client = TestClient(app)
        try:
            r = client.post(
                "/webhooks/evolution",
                json=_evolution_payload("WH-PRO", PRO_PHONE + "@s.whatsapp.net"),
            )
            assert r.status_code == 200
            assert scheduled.get("user_id") == DEV_USER_ID
            assert scheduled.get("text") == "quero marcar"
        finally:
            _purge("WH-PRO")
            restore = SessionLocal()
            u = restore.get(User, DEV_USER_ID)
            u.phone = previous
            restore.commit()
            restore.close()


def test_evolution_duplicate_is_acked_without_reprocessing(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    client = TestClient(app)
    try:
        p = _evolution_payload("WH-DUP", "5551911110000@s.whatsapp.net")
        r1 = client.post("/webhooks/evolution", json=p)
        r2 = client.post("/webhooks/evolution", json=p)
        assert r1.status_code == 200 and r2.status_code == 200
        db = SessionLocal()
        try:
            count = db.query(InboundMessageRecord).filter(
                InboundMessageRecord.provider_message_id == "WH-DUP"
            ).count()
            assert count == 1
        finally:
            db.close()
    finally:
        _purge("WH-DUP")
