# tests/integration/test_ingestion_service.py
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.channels.inbound import InboundMessage
from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.models.inbound_message import InboundMessageRecord
from app.models.user import User
from app.services import agent_runner, ingestion_service
from app.services.ingestion_service import IngestionService, dispatch_agent_run

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
PRO_PHONE = "+5551977776666"
LEAD_PHONE = "5551911110000"


def _make(provider_message_id, sender_phone, text="oi"):
    return InboundMessage(
        provider="evolution",
        sender_phone=sender_phone,
        text=text,
        provider_message_id=provider_message_id,
        timestamp=datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        recipient_phone=None,
        raw={"event": "messages.upsert"},
    )


def _purge_inbound(db, *ids):
    db.query(InboundMessageRecord).filter(
        InboundMessageRecord.provider_message_id.in_(ids)
    ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def db_user_phone():
    db = SessionLocal()
    user = db.get(User, DEV_USER_ID)
    previous = user.phone
    user.phone = PRO_PHONE
    db.commit()
    yield
    restore = SessionLocal()
    try:
        u = restore.get(User, DEV_USER_ID)
        u.phone = previous
        restore.commit()
    finally:
        restore.close()
    db.close()


def test_known_professional_is_classified_and_recorded(db_user_phone):
    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-PRO-1", PRO_PHONE))
        assert res.status == "professional"
        assert res.user_id == DEV_USER_ID
        rec = db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == "MID-PRO-1"
        ).one()
        assert rec.classification == "professional"
        assert rec.user_id == DEV_USER_ID
    finally:
        _purge_inbound(db, "MID-PRO-1")
        db.close()


def test_unknown_number_is_parked_as_lead():
    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-LEAD-1", LEAD_PHONE))
        assert res.status == "lead"
        assert res.user_id is None
        rec = db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == "MID-LEAD-1"
        ).one()
        assert rec.classification == "lead"
        assert rec.user_id is None
    finally:
        _purge_inbound(db, "MID-LEAD-1")
        db.close()


def test_duplicate_message_is_not_processed_twice():
    db = SessionLocal()
    try:
        first = IngestionService(db).handle(_make("MID-DUP-1", LEAD_PHONE))
        assert first.status == "lead"
        second = IngestionService(db).handle(_make("MID-DUP-1", LEAD_PHONE))
        assert second.status == "duplicate"
        count = db.query(InboundMessageRecord).filter(
            InboundMessageRecord.provider_message_id == "MID-DUP-1"
        ).count()
        assert count == 1
    finally:
        _purge_inbound(db, "MID-DUP-1")
        db.close()


async def test_dispatch_agent_run_persists_a_turn(db_user_phone, monkeypatch):
    monkeypatch.setattr(ingestion_service, "build_calendar_access", lambda db, user, settings: None, raising=False)
    monkeypatch.setattr(agent_runner, "build_calendar_access", lambda db, user, settings: None)

    def _noop(messages, info):
        return ModelResponse(parts=[TextPart("noop")])

    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("resposta via webhook")])

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.simplifica_agent import build_simplifica_agent
        agent = build_simplifica_agent()
    monkeypatch.setattr(ingestion_service, "build_simplifica_agent", lambda: agent)

    inbound = _make("MID-RUN-1", PRO_PHONE)
    db = SessionLocal()
    try:
        res = IngestionService(db).handle(inbound)
        record_id = res.record_id
    finally:
        db.close()

    with agent.override(model=FunctionModel(scripted)):
        await dispatch_agent_run(inbound, DEV_USER_ID, record_id)

    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(
            ChatSession.user_id == DEV_USER_ID,
            ChatSession.phone_number == inbound.sender_phone,
        ).first()
        assert session is not None
        msgs = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.asc()).all()
        assert [m.message_type for m in msgs] == ["user", "assistant"]
        assert msgs[1].content == "resposta via webhook"
        db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete(
            synchronize_session=False
        )
        db.query(ChatSession).filter(ChatSession.id == session.id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        _purge_inbound(db, "MID-RUN-1")
        db.close()


async def test_dispatch_marks_agent_run_at(db_user_phone, monkeypatch):
    from app.models.inbound_message import InboundMessageRecord

    monkeypatch.setattr(agent_runner, "build_calendar_access", lambda db, user, settings: None, raising=False)

    def _noop(messages, info):
        return ModelResponse(parts=[TextPart("noop")])

    async def scripted(messages, info):
        return ModelResponse(parts=[TextPart("ok")])

    with patch("app.agents.simplifica_agent.get_llm_model", return_value=FunctionModel(_noop)):
        from app.agents.simplifica_agent import build_simplifica_agent
        agent = build_simplifica_agent()
    monkeypatch.setattr(ingestion_service, "build_simplifica_agent", lambda: agent)

    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-MARK-1", PRO_PHONE))
        assert res.status == "professional"
        record_id = res.record_id
    finally:
        db.close()

    inbound = _make("MID-MARK-1", PRO_PHONE)
    with agent.override(model=FunctionModel(scripted)):
        await dispatch_agent_run(inbound, DEV_USER_ID, record_id)

    db = SessionLocal()
    try:
        rec = db.get(InboundMessageRecord, record_id)
        assert rec.agent_run_at is not None
    finally:
        _purge_inbound(db, "MID-MARK-1")
        db.close()


async def test_dispatch_is_skipped_when_already_run(db_user_phone, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.core.config import settings as _settings
    from app.models.inbound_message import InboundMessageRecord

    ran = {"called": False}

    async def boom(*a, **k):
        ran["called"] = True
        raise AssertionError("agent must not run for an already-marked record")

    monkeypatch.setattr(ingestion_service, "process_professional_message", boom)

    db = SessionLocal()
    try:
        res = IngestionService(db).handle(_make("MID-SKIP-1", PRO_PHONE))
        rec = db.get(InboundMessageRecord, res.record_id)
        rec.agent_run_at = datetime.now(ZoneInfo(_settings.TIMEZONE))
        db.commit()
        record_id = res.record_id
    finally:
        db.close()

    await dispatch_agent_run(_make("MID-SKIP-1", PRO_PHONE), DEV_USER_ID, record_id)
    assert ran["called"] is False

    db = SessionLocal()
    try:
        _purge_inbound(db, "MID-SKIP-1")
    finally:
        db.close()
