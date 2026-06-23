"""Multi-turn driver: run a conversation against a real agent with a pinned model,
collecting tool calls, transcript, DB snapshot, tokens and latency."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from uuid import UUID

from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from app.agents.foundation import get_llm_run_metadata
from app.agents.history import to_model_messages
from app.core.database import SessionLocal
from app.services.chat_history_service import ChatHistoryService

# Dedicated, isolated eval principal (never the dev user).
EVAL_USER_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
EVAL_PHONE = "+5551900000000"
RAW_HISTORY_LIMIT = 10


@dataclass
class CaseInputs:
    agent: str  # "pro" | "lead"
    messages: list[str]
    setup: dict | None = None


@dataclass
class ToolCall:
    name: str
    args: dict
    success: bool | None


@dataclass
class Turn:
    user: str
    assistant: str


@dataclass
class DbSnapshot:
    clients: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    lead: dict | None = None


@dataclass
class CaseResult:
    tool_calls: list[ToolCall]
    final_output: str
    transcript: list[Turn]
    db: DbSnapshot
    tokens: int
    latency_ms: int
    model: str


def _coerce_args(raw) -> dict:
    """Return a dict from ToolCallPart.args, which may be a dict or a JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return {}


def extract_tool_calls(messages) -> list[ToolCall]:
    """Pair ToolCallParts (args) with their ToolReturnParts (success) from a run."""
    calls: dict[str, ToolCall] = {}
    order: list[str] = []
    for m in messages:
        for part in getattr(m, "parts", []):
            if isinstance(part, ToolCallPart):
                args = _coerce_args(part.args)
                key = f"{part.tool_name}:{len(order)}"
                calls[key] = ToolCall(name=part.tool_name, args=args, success=None)
                order.append(key)
            elif isinstance(part, ToolReturnPart):
                # attach to the most recent unresolved call of this tool
                for key in reversed(order):
                    if calls[key].name == part.tool_name and calls[key].success is None:
                        content = part.content if isinstance(part.content, dict) else {}
                        calls[key] = ToolCall(
                            name=calls[key].name, args=calls[key].args,
                            success=content.get("success"),
                        )
                        break
    return [calls[k] for k in order]


def _purge(db) -> None:
    from app.models.chat_session import ChatMessage, ChatSession
    from app.models.client import Client
    from app.models.event import Event
    from app.models.lead import Lead
    from app.models.user import User
    for s in db.query(ChatSession).filter(
        (ChatSession.user_id == EVAL_USER_ID) | (ChatSession.phone_number == EVAL_PHONE)
    ):
        db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete(synchronize_session=False)
    db.query(ChatSession).filter(
        (ChatSession.user_id == EVAL_USER_ID) | (ChatSession.phone_number == EVAL_PHONE)
    ).delete(synchronize_session=False)
    db.query(Event).filter(Event.user_id == EVAL_USER_ID).delete(synchronize_session=False)
    db.query(Client).filter(Client.user_id == EVAL_USER_ID).delete(synchronize_session=False)
    db.query(Lead).filter(Lead.phone == EVAL_PHONE).delete(synchronize_session=False)
    db.query(User).filter(User.phone == EVAL_PHONE).delete(synchronize_session=False)
    db.commit()


def _ensure_eval_user(db):
    from app.models.user import User
    u = db.get(User, EVAL_USER_ID)
    if u is None:
        u = User(id=EVAL_USER_ID, name="Eval User", email="eval-user@simplificapsi.test", phone=EVAL_PHONE)
        db.add(u)
        db.commit()
    return u


def _apply_setup(db, inputs: CaseInputs) -> None:
    """Seed pre-existing rows a case needs (e.g. a registered client)."""
    from decimal import Decimal

    from app.models.client import Client
    for c in (inputs.setup or {}).get("clients", []):
        db.add(Client(
            user_id=EVAL_USER_ID, name=c["name"], phone=c["phone"],
            invoice_day=c.get("invoice_day", 10),
            consult_price=Decimal(str(c.get("consult_price", 200))), is_active=True,
        ))
    db.commit()


def _snapshot(db, inputs: CaseInputs) -> DbSnapshot:
    from app.models.client import Client
    from app.models.event import Event
    from app.models.lead import Lead
    clients = [
        {"name": c.name, "phone": c.phone, "consult_price": str(c.consult_price),
         "invoice_day": c.invoice_day, "is_active": c.is_active}
        for c in db.query(Client).filter(Client.user_id == EVAL_USER_ID)
    ]
    events = [
        {"status": e.status, "billable": e.billable, "is_recurring": e.is_recurring,
         "recurrence_rule": e.recurrence_rule}
        for e in db.query(Event).filter(Event.user_id == EVAL_USER_ID)
    ]
    lead_row = db.query(Lead).filter(Lead.phone == EVAL_PHONE).first()
    lead = None if lead_row is None else {
        "status": lead_row.status, "name": lead_row.name, "converted": lead_row.user_id is not None,
    }
    return DbSnapshot(clients=clients, events=events, lead=lead)


async def run_case(inputs: CaseInputs, model, *, db_factory=SessionLocal) -> CaseResult:
    """Drive a multi-turn conversation against the chosen agent with `model` pinned."""
    from app.agents.lead_agent import build_lead_agent
    from app.agents.simplifica_agent import build_simplifica_agent
    from app.services.agent_runner import build_agent_deps, build_lead_deps
    from app.services.lead_service import LeadService

    db = db_factory()
    all_messages: list = []
    transcript: list[Turn] = []
    tokens = 0
    final_output = ""
    try:
        _purge(db)
        history = ChatHistoryService(db)
        if inputs.agent == "lead":
            agent = build_lead_agent()
            lead = LeadService(db).get_or_create_lead(EVAL_PHONE)
        else:
            agent = build_simplifica_agent()
            user = _ensure_eval_user(db)
            _apply_setup(db, inputs)

        t0 = time.monotonic()
        with agent.override(model=model):
            for msg in inputs.messages:
                if inputs.agent == "lead":
                    session = history.get_or_create_lead_session(lead.id, EVAL_PHONE)
                    deps = build_lead_deps(db, lead, history_summary=session.summary)
                else:
                    session = history.get_or_create_session(EVAL_USER_ID, EVAL_PHONE)
                    deps = build_agent_deps(db, user, history_summary=session.summary)
                message_history = to_model_messages(history.recent_messages(session, RAW_HISTORY_LIMIT))
                result = await agent.run(msg, deps=deps, message_history=message_history)
                final_output = result.output
                all_messages.extend(result.all_messages())
                transcript.append(Turn(user=msg, assistant=result.output))
                history.append_turn(session, msg, result.output)
                meta = get_llm_run_metadata(result) or {}
                tokens += int((meta.get("token_usage") or {}).get("total", 0) or 0)
        latency_ms = int((time.monotonic() - t0) * 1000)
        snapshot = _snapshot(db, inputs)
    finally:
        try:
            db.rollback()
            _purge(db)
        except Exception:
            db.rollback()
        finally:
            db.close()

    return CaseResult(
        tool_calls=extract_tool_calls(all_messages),
        final_output=final_output,
        transcript=transcript,
        db=snapshot,
        tokens=tokens,
        latency_ms=latency_ms,
        model=getattr(model, "model_name", str(model)),
    )
