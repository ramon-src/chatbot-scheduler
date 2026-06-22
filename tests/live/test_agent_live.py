"""End-to-end functional tests against the REAL LLM + real Google Calendar.

Skipped unless RUN_LIVE=1 and the required credentials are present. Run with:

    make test-live          # RUN_LIVE=1 uv run pytest -m live -s -v

These tests cost LLM tokens and create/delete real Google Calendar events under
the service account. They use an isolated test user and clean up after themselves.

Assertions read the TOOL return values from the agent's message history (what
*our* code produced), not the LLM's free-text rephrasing — so they are
deterministic about behavior (e.g. the timezone formatting) while still routing
tool selection through the real LLM.
"""

import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.live

# Quiet the very chatty HTTP/Google debug logs so the test output stays readable.
for _noisy in ("httpx", "httpcore", "openai", "google_auth_httplib2", "googleapiclient"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

TZ = ZoneInfo("America/Sao_Paulo")
TEST_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_CLIENT_NAME = "Maria Silva"
TEST_CLIENT_PHONE = "+5551999990000"


def _require_live():
    if not os.environ.get("RUN_LIVE"):
        pytest.skip("set RUN_LIVE=1 to run live end-to-end tests")
    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY not set")
    from app.services.google_auth import service_account_available

    if not service_account_available(settings):
        pytest.skip("service account (GOOGLE_CLIENT_EMAIL/GOOGLE_PRIVATE_KEY) not configured")


def _tool_returns(result, tool_name):
    """Extract the dicts returned by a given tool from the agent run history."""
    from pydantic_ai.messages import ToolReturnPart

    out = []
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                out.append(part.content)
    return out


def _purge(db):
    from app.core.config import settings
    from app.models.calendar import Calendar
    from app.models.client import Client
    from app.models.event import Event
    from app.models.google_credential import GoogleCredential
    from app.models.user import User
    from app.services.calendar_provider import build_calendar_access

    user = db.get(User, TEST_USER_ID)
    # best-effort: delete real Google events + the test calendar under the SA
    if user is not None:
        try:
            access = build_calendar_access(db, user, settings)
            svc = access.service if access else None
        except Exception:
            svc = None
        if svc is not None:
            for ev in db.query(Event).filter(Event.user_id == TEST_USER_ID):
                if ev.google_event_id:
                    try:
                        svc.cancel_event(ev.google_event_id)
                    except Exception:
                        pass
            cal = db.query(Calendar).filter(
                Calendar.user_id == TEST_USER_ID, Calendar.is_primary == True  # noqa: E712
            ).first()
            if cal and cal.google_calendar_id and cal.google_calendar_id != "primary":
                try:
                    svc.delete_calendar(cal.google_calendar_id)
                except Exception:
                    pass
    for model in (Event, Client, Calendar, GoogleCredential):
        db.query(model).filter(model.user_id == TEST_USER_ID).delete(synchronize_session=False)
    db.query(User).filter(User.id == TEST_USER_ID).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(scope="module")
def live():
    _require_live()
    from app.agents.simplifica_agent import build_simplifica_agent
    from app.api.agent_routes import _build_agent_deps
    from app.core.database import SessionLocal
    from app.models.client import Client
    from app.models.user import User

    db = SessionLocal()
    _purge(db)  # clean slate

    db.add(User(id=TEST_USER_ID, name="Teste Live", email="teste-live@simplificapsi.test"))
    db.add(Client(
        user_id=TEST_USER_ID, name=TEST_CLIENT_NAME, phone=TEST_CLIENT_PHONE,
        invoice_day=10, consult_price=Decimal("200"), is_active=True,
    ))
    db.commit()

    async def send(msg: str):
        agent = build_simplifica_agent()
        user = db.get(User, TEST_USER_ID)
        deps = _build_agent_deps(db, user)
        return await agent.run(msg, deps=deps)

    try:
        yield SimpleNamespace(send=send, db=db)
    finally:
        _purge(db)
        db.close()


async def test_schedule_creates_event_at_local_time(live):
    from app.models.event import Event

    tomorrow = (datetime.now(TZ) + timedelta(days=1)).date()
    result = await live.send(f"agenda a {TEST_CLIENT_NAME} amanhã às 10h")

    creates = _tool_returns(result, "create_event")
    assert creates, f"create_event was not called. Output: {result.output!r}"
    assert creates[-1]["success"] is True, creates[-1]

    ev = (
        live.db.query(Event)
        .filter(Event.user_id == TEST_USER_ID, Event.status != "cancelled")
        .order_by(Event.created_at.desc())
        .first()
    )
    assert ev is not None, "no Event row persisted"
    assert ev.google_event_id, "event was not created on Google (no google_event_id)"
    local = ev.start_time.astimezone(TZ)
    assert local.date() == tomorrow
    assert local.hour == 10, f"expected 10h local, got {local.isoformat()}"


async def test_list_shows_local_time(live):
    """Regression for the UTC display bug: the list tool message must say 10h, not 13h."""
    result = await live.send("o que eu tenho para amanhã?")

    lists = _tool_returns(result, "list_events")
    assert lists, f"list_events was not called. Output: {result.output!r}"
    msg = lists[-1]["message"]
    assert "10h" in msg, f"expected local 10h in tool message, got: {msg!r}"
    assert "13h" not in msg, f"event leaked in UTC: {msg!r}"


async def test_unknown_client_is_rejected(live):
    from app.models.event import Event

    before = live.db.query(Event).filter(Event.user_id == TEST_USER_ID).count()
    result = await live.send("agenda o Carlos Inexistente Mendes amanhã às 16h")

    creates = _tool_returns(result, "create_event")
    # Either the tool was not called, or it was called and returned success=False.
    if creates:
        assert creates[-1]["success"] is False, "scheduled an event for a non-existent client"
    after = live.db.query(Event).filter(Event.user_id == TEST_USER_ID).count()
    assert after == before, "an orphan event was created for an unknown client"


async def test_cancel_removes_event(live):
    from app.models.event import Event

    result = await live.send(f"cancela a sessão da {TEST_CLIENT_NAME} amanhã")
    cancels = _tool_returns(result, "cancel_event")
    assert cancels, f"cancel_event was not called. Output: {result.output!r}"
    assert cancels[-1]["success"] is True, cancels[-1]

    active = (
        live.db.query(Event)
        .filter(Event.user_id == TEST_USER_ID, Event.status != "cancelled")
        .count()
    )
    assert active == 0, "event was not cancelled in the Postgres mirror"
