"""Shared fixture + helpers for the live functional tests (real LLM + Google).

Everything the live tests need is exposed on the `live` fixture object (so test
modules need no cross-module imports): `live.send`, `live.db`, `live.tool_returns`,
and the constants `live.tz / live.user_id / live.client_name / live.client_phone`.
"""

import os
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

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
    """Delete the test user's Google calendar/events + all its DB rows."""
    from app.core.config import settings
    from app.models.calendar import Calendar
    from app.models.client import Client
    from app.models.event import Event
    from app.models.google_credential import GoogleCredential
    from app.models.user import User
    from app.services.calendar_provider import build_calendar_access

    user = db.get(User, TEST_USER_ID)
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
    """Isolated test user + one client; a send() helper that drives the real agent."""
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
        yield SimpleNamespace(
            send=send, db=db, tool_returns=_tool_returns,
            tz=TZ, user_id=TEST_USER_ID,
            client_name=TEST_CLIENT_NAME, client_phone=TEST_CLIENT_PHONE,
        )
    finally:
        _purge(db)
        db.close()
