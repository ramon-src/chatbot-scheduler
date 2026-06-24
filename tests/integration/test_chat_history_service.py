# tests/integration/test_chat_history_service.py
from uuid import UUID

import pytest

from app.core.database import SessionLocal
from app.models.chat_session import ChatMessage, ChatSession
from app.services.chat_history_service import ChatHistoryService

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
TEST_PHONE = "+5500000000000"


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    # cleanup any sessions/messages created against the test phone
    rows = session.query(ChatSession).filter(ChatSession.phone_number == TEST_PHONE).all()
    for s in rows:
        session.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(
            synchronize_session=False
        )
    session.query(ChatSession).filter(ChatSession.phone_number == TEST_PHONE).delete(
        synchronize_session=False
    )
    session.commit()
    session.close()


def test_get_or_create_session_creates_then_reuses(db):
    svc = ChatHistoryService(db)
    s1 = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE)
    s2 = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE)
    assert s1.id == s2.id
    assert s1.phone_number == TEST_PHONE


def test_different_phone_gets_different_session(db):
    svc = ChatHistoryService(db)
    s1 = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE)
    s2 = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE + "1")
    try:
        assert s1.id != s2.id
    finally:
        db.query(ChatMessage).filter(ChatMessage.session_id == s2.id).delete(
            synchronize_session=False
        )
        db.query(ChatSession).filter(ChatSession.id == s2.id).delete(synchronize_session=False)
        db.commit()


def test_append_turn_persists_user_then_assistant_in_order(db):
    svc = ChatHistoryService(db)
    s = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE)
    svc.append_turn(s, "lista meus clientes", "Você tem 2 clientes ativos.")

    msgs = svc.recent_messages(s, limit=10)
    assert [m.message_type for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "lista meus clientes"
    assert msgs[1].content == "Você tem 2 clientes ativos."


def test_recent_messages_returns_last_n_chronological(db):
    svc = ChatHistoryService(db)
    s = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE)
    for i in range(4):
        svc.append_turn(s, f"pergunta {i}", f"resposta {i}")  # 8 messages total

    recent = svc.recent_messages(s, limit=3)
    assert len(recent) == 3
    # chronological ascending, and these are the most recent rows
    assert recent[-1].content == "resposta 3"


def test_unsummarized_overflow_returns_messages_beyond_window(db):
    svc = ChatHistoryService(db)
    s = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE)
    for i in range(4):
        svc.append_turn(s, f"p{i}", f"r{i}")  # 8 messages

    overflow = svc.unsummarized_overflow(s, keep_recent=3)
    assert len(overflow) == 5
    assert overflow[0].content == "p0"  # oldest first


def test_fold_summary_advances_marker_and_stops_resummarizing(db):
    svc = ChatHistoryService(db)
    s = svc.get_or_create_session(DEV_USER_ID, TEST_PHONE)
    for i in range(4):
        svc.append_turn(s, f"p{i}", f"r{i}")  # 8 messages

    pending = svc.unsummarized_overflow(s, keep_recent=3)
    svc.fold_summary(s, "resumo dos 5 primeiros", summarized_count=len(pending))
    db.refresh(s)
    assert s.summary == "resumo dos 5 primeiros"
    assert s.summarized_count == 5

    # nothing new to summarize until more overflow accrues
    assert svc.unsummarized_overflow(s, keep_recent=3) == []

    # two more messages -> exactly two new overflow items, not the whole history
    svc.append_turn(s, "p4", "r4")  # 10 messages; keep 3 -> overflow up to idx 7
    pending2 = svc.unsummarized_overflow(s, keep_recent=3)
    assert [m.content for m in pending2] == ["r2", "p3"]
