# tests/integration/test_orphan_resweep.py
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.inbound_message import InboundMessageRecord

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


def _evo_payload(message_id, remote_jid, text="oi"):
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


def _seed_orphan(message_id, *, minutes_old, agent_run_at=None, user_id=DEV_USER_ID,
                 classification="professional"):
    db = SessionLocal()
    try:
        rec = InboundMessageRecord(
            provider="evolution", provider_message_id=message_id,
            sender_phone="5551000000000", recipient_phone=None, text="oi",
            classification=classification, user_id=user_id, raw={"k": "v"},
            agent_run_at=agent_run_at,
        )
        db.add(rec)
        db.flush()
        rec.received_at = datetime.now(UTC) - timedelta(minutes=minutes_old)
        db.commit()
        return rec.id
    finally:
        db.close()


def _purge(*ids):
    db = SessionLocal()
    try:
        db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id.in_(ids)
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_old_unrun_professional_orphan_is_redispatched(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    orphan_id = _seed_orphan("ORPH-OLD", minutes_old=5)
    scheduled = []

    async def fake_dispatch(inbound, user_id, record_id):
        scheduled.append((record_id, user_id, inbound.text))

    try:
        with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
            client = TestClient(app)
            # A fresh LEAD message (unknown number) — current message won't dispatch,
            # isolating the orphan sweep.
            r = client.post("/webhooks/evolution",
                            json=_evo_payload("SWEEP-TRIGGER", "5551911110000@s.whatsapp.net"))
            assert r.status_code == 200
        assert any(rid == orphan_id for rid, _, _ in scheduled), scheduled
    finally:
        _purge("ORPH-OLD", "SWEEP-TRIGGER")


def test_recent_orphan_is_not_redispatched(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    orphan_id = _seed_orphan("ORPH-RECENT", minutes_old=0)
    scheduled = []

    async def fake_dispatch(inbound, user_id, record_id):
        scheduled.append(record_id)

    try:
        with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
            client = TestClient(app)
            r = client.post("/webhooks/evolution",
                            json=_evo_payload("SWEEP-TRIGGER-2", "5551911110000@s.whatsapp.net"))
            assert r.status_code == 200
        assert orphan_id not in scheduled
    finally:
        _purge("ORPH-RECENT", "SWEEP-TRIGGER-2")


def test_already_run_orphan_is_not_redispatched(monkeypatch):
    monkeypatch.setattr(settings, "EVOLUTION_WEBHOOK_TOKEN", None)
    run_at = datetime.now(UTC) - timedelta(minutes=1)
    orphan_id = _seed_orphan("ORPH-DONE", minutes_old=5, agent_run_at=run_at)
    scheduled = []

    async def fake_dispatch(inbound, user_id, record_id):
        scheduled.append(record_id)

    try:
        with patch("app.api.webhook_routes.dispatch_agent_run", side_effect=fake_dispatch):
            client = TestClient(app)
            r = client.post("/webhooks/evolution",
                            json=_evo_payload("SWEEP-TRIGGER-3", "5551911110000@s.whatsapp.net"))
            assert r.status_code == 200
        assert orphan_id not in scheduled
    finally:
        _purge("ORPH-DONE", "SWEEP-TRIGGER-3")
