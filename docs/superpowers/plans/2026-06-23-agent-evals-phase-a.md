# Agent Evals — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation of the agent eval harness — pinned single-OpenAI-model runs, a multi-turn driver, deterministic + DB evaluators, a Google-free dataset (Lead + Cliente + Formato, including the slot-filling regression case), and a `make eval-fast` runner with a per-category report.

**Architecture:** `pydantic_evals` `Dataset` of `Case`s. Each case is a multi-turn conversation driven against the real agent with a single OpenAI model pinned via `agent.override(model=...)`. The driver returns a structured `CaseResult` (tool calls, final text, DB snapshot, tokens, latency); custom `Evaluator`s score it. Phase A is Google-free (Lead + Cliente + Formato); agenda and the multi-model matrix are Phases B/C (separate plans).

**Tech Stack:** Python 3.11+, `pydantic_evals`, Pydantic AI (`OpenAIChatModel`, `FunctionModel` for tests), SQLAlchemy, pytest (asyncio_mode=auto).

## Global Constraints

- All eval code lives under `evals/` (top-level, NOT under `tests/`); it is opt-in and costs tokens.
- Real-LLM runs are gated by `RUN_EVAL=1` and require `OPENAI_API_KEY`; without it they skip with a message.
- Unit tests for the harness/evaluators use `FunctionModel` and synthetic `CaseResult` — NO real LLM, NO Google. They run in the normal suite.
- Pin a SINGLE OpenAI model per run (not the `FallbackModel` chain), built directly as `OpenAIChatModel` with `seed=0` and low temperature for determinism.
- Code/identifiers/enums in English; agent-facing copy stays PT-BR.
- Tool contract: agent tool returns `{"success","data","message"}`; eval `NoLeakage` asserts the agent's final text has no IDs/JSON/URL/`**`.
- DB schema `simplificapsi`; timezone `America/Sao_Paulo`. Eval isolation uses a dedicated eval user UUID, distinct from the dev user `550e8400-...`.
- Commits never attribute to AI.
- Concrete OpenAI model IDs (from `app/agents/foundation/llm.py`): `gpt-5.4-mini` → `gpt-5.4-mini-2026-03-17`, `gpt-5.4-nano` → `gpt-5.4-nano`, `gpt-5.4` → `gpt-5.4-2026-03-05`.

---

### Task 1: evals package + pinned OpenAI model

**Files:**
- Create: `evals/__init__.py`, `evals/models.py`, `tests/unit/test_eval_models.py`

**Interfaces:**
- Produces:
  - `evals.models.EVAL_MODELS: dict[str, str]` — alias → concrete OpenAI id.
  - `evals.models.build_eval_model(alias: str, temperature: float = 0.1, timeout: int = 30) -> OpenAIChatModel` — a single pinned OpenAI model (raises `KeyError` on unknown alias).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_eval_models.py
import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from evals.models import EVAL_MODELS, build_eval_model


def test_known_aliases_map_to_concrete_ids():
    assert EVAL_MODELS["gpt-5.4-mini"] == "gpt-5.4-mini-2026-03-17"
    assert EVAL_MODELS["gpt-5.4-nano"] == "gpt-5.4-nano"
    assert EVAL_MODELS["gpt-5.4"] == "gpt-5.4-2026-03-05"


def test_build_eval_model_returns_single_openai_model():
    m = build_eval_model("gpt-5.4-mini")
    assert isinstance(m, OpenAIChatModel)
    # the concrete model id, not the alias
    assert "gpt-5.4-mini-2026-03-17" in repr(m) or m.model_name == "gpt-5.4-mini-2026-03-17"


def test_unknown_alias_raises():
    with pytest.raises(KeyError):
        build_eval_model("does-not-exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_eval_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals'`.

- [ ] **Step 3: Implement**

```python
# evals/__init__.py
"""Opt-in agent evaluation harness (real LLM). Not part of the normal test suite."""
```

```python
# evals/models.py
"""Pin a single OpenAI model (no FallbackModel chain) for clean per-model evals."""

from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

# alias -> concrete OpenAI model id (mirrors app/agents/foundation/llm.py)
EVAL_MODELS: dict[str, str] = {
    "gpt-5.4-mini": "gpt-5.4-mini-2026-03-17",
    "gpt-5.4-nano": "gpt-5.4-nano",
    "gpt-5.4": "gpt-5.4-2026-03-05",
}


def build_eval_model(alias: str, temperature: float = 0.1, timeout: int = 30) -> OpenAIChatModel:
    """Build a single pinned OpenAI model for `agent.override(model=...)`.

    Deterministic (seed=0, low temperature) so eval results are reproducible.
    Raises KeyError for an unknown alias.
    """
    concrete = EVAL_MODELS[alias]
    return OpenAIChatModel(
        concrete,
        settings=OpenAIChatModelSettings(timeout=timeout, temperature=temperature, seed=0),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_eval_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add evals/__init__.py evals/models.py tests/unit/test_eval_models.py
git commit -m "feat(evals): evals package + pinned single OpenAI model"
```

---

### Task 2: multi-turn harness driver

**Files:**
- Create: `evals/harness.py`, `tests/unit/test_eval_harness.py`

**Interfaces:**
- Consumes: `build_simplifica_agent` (`app/agents/simplifica_agent`), `build_lead_agent` (`app/agents/lead_agent`), `build_agent_deps`/`build_lead_deps` (`app/services/agent_runner`), `ChatHistoryService` (`app/services/chat_history_service`), `to_model_messages` (`app/agents/history`), `LeadService` (`app/services/lead_service`), `get_llm_run_metadata` (`app/agents/foundation`).
- Produces (dataclasses + driver):
  - `CaseInputs(agent: str, messages: list[str], setup: dict | None = None)` — `agent` is `"pro"` or `"lead"`.
  - `ToolCall(name: str, args: dict, success: bool | None)`
  - `Turn(user: str, assistant: str)`
  - `DbSnapshot(clients: list[dict], events: list[dict], lead: dict | None)`
  - `CaseResult(tool_calls: list[ToolCall], final_output: str, transcript: list[Turn], db: DbSnapshot, tokens: int, latency_ms: int, model: str)`
  - `extract_tool_calls(result) -> list[ToolCall]` — pulls `ToolCallPart`/`ToolReturnPart` pairs from `result.all_messages()`.
  - `async def run_case(inputs: CaseInputs, model, *, db_factory=SessionLocal) -> CaseResult`

**Context:** The driver mirrors `tests/live/conftest.py::send_memory` (build agent → build deps with `session.summary` → `agent.run(msg, deps, message_history)` → persist turn) but captures each turn's `result` so tool calls can be extracted. It uses a dedicated EVAL user/lead (UUID `eeee...`) and purges that user's rows before each case for isolation.

- [ ] **Step 1: Write the failing test (FunctionModel — no real LLM)**

```python
# tests/unit/test_eval_harness.py
from pydantic_ai.messages import (
    ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from evals.harness import CaseInputs, extract_tool_calls, run_case


def test_extract_tool_calls_pairs_calls_with_returns():
    # one assistant message with a tool call, then a tool-return message
    msgs = [
        ModelResponse(parts=[ToolCallPart(tool_name="create_client", args={"name": "Ana Souza"})]),
        ModelRequest(parts=[ToolReturnPart(
            tool_name="create_client",
            content={"success": True, "data": {"name": "Ana Souza"}, "message": "ok"},
        )]),
    ]
    calls = extract_tool_calls(msgs)
    assert len(calls) == 1
    assert calls[0].name == "create_client"
    assert calls[0].args["name"] == "Ana Souza"
    assert calls[0].success is True


async def test_run_case_drives_lead_conversation_and_collects(monkeypatch):
    # Scripted model: always replies with text (no tools) so we exercise the driver,
    # not the real LLM. Build the lead agent under a patched get_llm_model.
    from unittest.mock import patch

    def reply(messages, info):
        return ModelResponse(parts=[TextPart("Oi! O Simplifica Psi te ajuda no consultório.")])

    with patch("app.agents.lead_agent.get_llm_model", return_value=FunctionModel(reply)):
        from app.agents.lead_agent import build_lead_agent  # noqa: F401  (import path proof)

    inputs = CaseInputs(agent="lead", messages=["oi", "como funciona?"])
    result = await run_case(inputs, FunctionModel(reply))

    assert result.model  # model label recorded
    assert len(result.transcript) == 2  # two user turns
    assert "Simplifica" in result.final_output
    assert result.tool_calls == []  # this scripted model called no tools
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_eval_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.harness'`.

- [ ] **Step 3: Implement**

```python
# evals/harness.py
"""Multi-turn driver: run a conversation against a real agent with a pinned model,
collecting tool calls, transcript, DB snapshot, tokens and latency."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from app.agents.foundation import get_llm_run_metadata
from app.agents.history import to_model_messages
from app.core.config import settings
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


def extract_tool_calls(messages) -> list[ToolCall]:
    """Pair ToolCallParts (args) with their ToolReturnParts (success) from a run."""
    calls: dict[str, ToolCall] = {}
    order: list[str] = []
    for m in messages:
        for part in getattr(m, "parts", []):
            if isinstance(part, ToolCallPart):
                args = part.args if isinstance(part.args, dict) else {}
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
        _purge(db)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_eval_harness.py -v`
Expected: PASS (2 tests). The driver builds the lead agent under the FunctionModel, runs 2 turns, collects an empty tool list and the scripted text.

- [ ] **Step 5: Commit**

```bash
git add evals/harness.py tests/unit/test_eval_harness.py
git commit -m "feat(evals): multi-turn harness driver (tool/transcript/db capture)"
```

---

### Task 3: deterministic evaluators (ToolSelected, ToolArgs, NoLeakage)

**Files:**
- Create: `evals/evaluators.py`, `tests/unit/test_eval_evaluators.py`

**Interfaces:**
- Consumes: `CaseResult`/`ToolCall` (Task 2), `pydantic_evals.evaluators.Evaluator`/`EvaluatorContext`.
- Produces three `Evaluator` subclasses scoring `ctx.output` (a `CaseResult`):
  - `ToolSelected(tool: str, success: bool | None = True)` → bool
  - `ToolArgs(tool: str, args: dict)` → bool (key args match, type-tolerant)
  - `NoLeakage()` → bool (final_output has no UUID/JSON/`http`/`**`)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_eval_evaluators.py
from types import SimpleNamespace

from evals.evaluators import NoLeakage, ToolArgs, ToolSelected
from evals.harness import CaseResult, DbSnapshot, ToolCall


def _ctx(result, metadata=None):
    # The evaluators only read ctx.output (and ctx.metadata); a stub avoids coupling
    # the test to pydantic_evals' EvaluatorContext constructor.
    return SimpleNamespace(output=result, metadata=metadata)


def _result(tool_calls, final_output="tudo certo"):
    return CaseResult(tool_calls=tool_calls, final_output=final_output, transcript=[],
                      db=DbSnapshot(), tokens=0, latency_ms=0, model="m")


def test_tool_selected_true_when_present_and_successful():
    r = _result([ToolCall("create_client", {"name": "Ana"}, True)])
    assert ToolSelected(tool="create_client").evaluate(_ctx(r)) is True
    assert ToolSelected(tool="cancel_event").evaluate(_ctx(r)) is False


def test_tool_args_match_is_type_tolerant():
    r = _result([ToolCall("create_client", {"consult_price": 200.0}, True)])
    assert ToolArgs(tool="create_client", args={"consult_price": 200}).evaluate(_ctx(r)) is True
    assert ToolArgs(tool="create_client", args={"consult_price": 999}).evaluate(_ctx(r)) is False


def test_no_leakage_flags_url_and_markdown():
    assert NoLeakage().evaluate(_ctx(_result([], "tudo certo, sem nada"))) is True
    assert NoLeakage().evaluate(_ctx(_result([], "veja em http://x.com"))) is False
    assert NoLeakage().evaluate(_ctx(_result([], "isso é **negrito**"))) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_eval_evaluators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.evaluators'`.

- [ ] **Step 3: Implement**

```python
# evals/evaluators.py
"""Custom pydantic_evals evaluators scoring a CaseResult."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _num_eq(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


@dataclass
class ToolSelected(Evaluator):
    tool: str
    success: bool | None = True

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        for c in ctx.output.tool_calls:
            if c.name == self.tool and (self.success is None or c.success == self.success):
                return True
        return False


@dataclass
class ToolArgs(Evaluator):
    tool: str
    args: dict

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        for c in ctx.output.tool_calls:
            if c.name != self.tool:
                continue
            if all(k in c.args and _num_eq(c.args[k], v) for k, v in self.args.items()):
                return True
        return False


@dataclass
class NoLeakage(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        text = ctx.output.final_output or ""
        if "http" in text.lower():
            return False
        if "**" in text:  # WhatsApp uses single-asterisk bold; ** renders literally
            return False
        if _UUID.search(text):
            return False
        if "{" in text and "}" in text and '":' in text:  # JSON-ish leak
            return False
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_eval_evaluators.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add evals/evaluators.py tests/unit/test_eval_evaluators.py
git commit -m "feat(evals): deterministic evaluators (ToolSelected, ToolArgs, NoLeakage)"
```

---

### Task 4: DbState evaluator

**Files:**
- Modify: `evals/evaluators.py`
- Test: `tests/unit/test_eval_db_state.py`

**Interfaces:**
- Produces: `DbState(check: dict)` `Evaluator` → bool. `check` keys:
  - `client_named: str` — a client whose name contains this exists.
  - `client_price: (name_substr, price)` — that client's `consult_price` equals price (type-tolerant).
  - `lead_converted: bool` — the lead snapshot is converted.
  - `event_cancelled_billable: bool` — at least one event with `status=="cancelled"` and matching `billable`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_eval_db_state.py
from types import SimpleNamespace

from evals.evaluators import DbState
from evals.harness import CaseResult, DbSnapshot


def _ctx(db: DbSnapshot):
    out = CaseResult(tool_calls=[], final_output="", transcript=[], db=db,
                     tokens=0, latency_ms=0, model="m")
    return SimpleNamespace(output=out, metadata=None)


def test_db_state_checks_client_presence_and_price():
    db = DbSnapshot(clients=[{"name": "Ana Souza", "consult_price": "220", "phone": "+5551999",
                              "invoice_day": 15, "is_active": True}])
    assert DbState(check={"client_named": "Ana"}).evaluate(_ctx(db)) is True
    assert DbState(check={"client_price": ["Ana", 220]}).evaluate(_ctx(db)) is True
    assert DbState(check={"client_price": ["Ana", 999]}).evaluate(_ctx(db)) is False
    assert DbState(check={"client_named": "Pedro"}).evaluate(_ctx(db)) is False


def test_db_state_checks_lead_converted():
    assert DbState(check={"lead_converted": True}).evaluate(
        _ctx(DbSnapshot(lead={"status": "converted", "name": "X", "converted": True}))) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_eval_db_state.py -v`
Expected: FAIL — `ImportError: cannot import name 'DbState'`.

- [ ] **Step 3: Implement (append to `evals/evaluators.py`)**

```python
@dataclass
class DbState(Evaluator):
    check: dict

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        db = ctx.output.db
        c = self.check
        if "client_named" in c:
            if not any(c["client_named"] in cl["name"] for cl in db.clients):
                return False
        if "client_price" in c:
            sub, price = c["client_price"]
            hit = [cl for cl in db.clients if sub in cl["name"]]
            if not hit or not _num_eq(hit[0]["consult_price"], price):
                return False
        if "lead_converted" in c:
            if not (db.lead and db.lead.get("converted") == c["lead_converted"]):
                return False
        if "event_cancelled_billable" in c:
            want = c["event_cancelled_billable"]
            if not any(e["status"] == "cancelled" and e["billable"] == want for e in db.events):
                return False
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_eval_db_state.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add evals/evaluators.py tests/unit/test_eval_db_state.py
git commit -m "feat(evals): DbState evaluator (client/lead/event outcomes)"
```

---

### Task 5: Google-free dataset (Lead + Cliente + Formato)

**Files:**
- Create: `evals/datasets/__init__.py`, `evals/datasets/google_free.py`, `tests/unit/test_eval_dataset.py`

**Interfaces:**
- Consumes: `Case`/`Dataset` (`pydantic_evals`), the evaluators (Tasks 3–4), `CaseInputs` (Task 2).
- Produces: `evals.datasets.google_free.build_google_free_dataset() -> Dataset` — a `Dataset` of `Case`s whose `inputs` are `CaseInputs` and whose `evaluators` are the deterministic ones. Includes the **slot-filling regression case** `cliente_slot_filling`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_eval_dataset.py
from evals.datasets.google_free import build_google_free_dataset
from evals.harness import CaseInputs


def test_dataset_builds_with_expected_cases():
    ds = build_google_free_dataset()
    names = {c.name for c in ds.cases}
    # key cases exist, including the slot-filling regression
    assert "cliente_criar_uma_msg" in names
    assert "cliente_slot_filling" in names
    assert "cliente_homonimo_pede_telefone" in names
    assert "lead_cria_conta" in names
    # all inputs are CaseInputs and the slot-filling case is multi-turn
    sf = next(c for c in ds.cases if c.name == "cliente_slot_filling")
    assert isinstance(sf.inputs, CaseInputs)
    assert len(sf.inputs.messages) >= 4  # fragmented across messages
    assert sf.evaluators  # has evaluators attached
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_eval_dataset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.datasets'`.

- [ ] **Step 3: Implement**

```python
# evals/datasets/__init__.py
```
(empty file)

```python
# evals/datasets/google_free.py
"""Google-free eval cases: Lead onboarding, Cliente CRUD, Formato."""

from __future__ import annotations

from pydantic_evals import Case, Dataset

from evals.evaluators import DbState, NoLeakage, ToolArgs, ToolSelected
from evals.harness import CaseInputs

_REGISTERED_MARIA = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
]}
_TWO_MARIAS = {"clients": [
    {"name": "Maria Silva", "phone": "+5551999990000", "invoice_day": 10, "consult_price": 200},
    {"name": "Maria Santos", "phone": "+5551988887777", "invoice_day": 5, "consult_price": 180},
]}


def build_google_free_dataset() -> Dataset:
    cases = [
        # ---- Lead / onboarding ----
        Case(
            name="lead_duvida_produto",
            inputs=CaseInputs(agent="lead", messages=["oi, o que é o simplifica psi?"]),
            evaluators=[NoLeakage()],
        ),
        Case(
            name="lead_cria_conta",
            inputs=CaseInputs(agent="lead", messages=[
                "quero começar a usar",
                "meu nome é Ramon Schmidt",
                "meu email é ramon@exemplo.com",
            ]),
            evaluators=[ToolSelected(tool="create_professional_account"),
                        DbState(check={"lead_converted": True}), NoLeakage()],
        ),
        # ---- Cliente CRUD ----
        Case(
            name="cliente_criar_uma_msg",
            inputs=CaseInputs(agent="pro", messages=[
                "cadastra a Ana Souza, telefone 51 98765-4321, dia de cobrança 15, consulta 220 reais",
            ]),
            evaluators=[ToolSelected(tool="create_client"),
                        DbState(check={"client_named": "Ana", "client_price": ["Ana", 220]}),
                        NoLeakage()],
        ),
        Case(
            name="cliente_slot_filling",  # REGRESSÃO do bug de coleta fragmentada
            inputs=CaseInputs(agent="pro", messages=[
                "quero cadastrar um cliente",
                "981321543",
                "joao silva",
                "10",
                "200",
            ]),
            evaluators=[ToolSelected(tool="create_client"),
                        DbState(check={"client_named": "Joao"}), NoLeakage()],
        ),
        Case(
            name="cliente_mudar_preco",
            inputs=CaseInputs(agent="pro", setup=_REGISTERED_MARIA,
                              messages=["muda o valor da consulta da Maria Silva para 250 reais"]),
            evaluators=[ToolSelected(tool="update_client"),
                        DbState(check={"client_price": ["Maria Silva", 250]}), NoLeakage()],
        ),
        Case(
            name="cliente_telefone_duplicado",
            inputs=CaseInputs(agent="pro", setup=_REGISTERED_MARIA, messages=[
                "cadastra o João Teste, telefone 51 99999-0000, dia 5, consulta 100 reais",
            ]),
            evaluators=[ToolSelected(tool="create_client", success=False), NoLeakage()],
        ),
        Case(
            name="cliente_homonimo_pede_telefone",
            inputs=CaseInputs(agent="pro", setup=_TWO_MARIAS,
                              messages=["agenda a Maria amanhã às 11h"]),
            # agent must NOT create an event/client blindly; it asks for the phone.
            evaluators=[NoLeakage()],
        ),
        # ---- Formato / segurança ----
        Case(
            name="formato_sem_markdown_url",
            inputs=CaseInputs(agent="lead", messages=["me explica os recursos e o preço"]),
            evaluators=[NoLeakage()],
        ),
    ]
    return Dataset(name="google_free", cases=cases)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_eval_dataset.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/datasets/__init__.py evals/datasets/google_free.py tests/unit/test_eval_dataset.py
git commit -m "feat(evals): google-free dataset (lead/cliente/formato + slot-filling regression)"
```

---

### Task 6: runner + report + make targets (validate with real LLM)

**Files:**
- Create: `evals/report.py`, `evals/run.py`
- Modify: `Makefile`
- Test: `tests/unit/test_eval_report.py`

**Interfaces:**
- Consumes: `build_google_free_dataset` (Task 5), `build_eval_model` (Task 1), `run_case`/`CaseResult` (Task 2), `Dataset.evaluate` (`pydantic_evals`).
- Produces:
  - `evals.report.summarize(report) -> str` — a markdown summary: per-case pass/fail, totals, avg tokens, avg latency. Pure function over a pydantic_evals `EvaluationReport`-like object (duck-typed: `.cases` with `.name`, `.scores`/`.assertions`, `.output`).
  - `evals.run.main(model_alias: str, case_filter: str | None) -> int` — builds the dataset, pins the model, runs `Dataset.evaluate`, prints the summary; returns process exit code (0 = all passed).

**Context:** `summarize` is unit-tested with a synthetic report object (no LLM). `run.main` is validated by actually running `make eval-fast` against the real LLM (no Google) — that is this task's acceptance check, not a unit test.

- [ ] **Step 1: Write the failing test (report summary, no LLM)**

```python
# tests/unit/test_eval_report.py
from types import SimpleNamespace

from evals.report import summarize


def _case(name, passed, tokens, latency):
    out = SimpleNamespace(tokens=tokens, latency_ms=latency)
    return SimpleNamespace(name=name, passed=passed, output=out)


def test_summarize_reports_totals_and_per_case():
    report = SimpleNamespace(cases=[
        _case("cliente_slot_filling", True, 1200, 3000),
        _case("cliente_telefone_duplicado", False, 800, 2000),
    ])
    text = summarize(report)
    assert "cliente_slot_filling" in text
    assert "1/2" in text or "1 / 2" in text  # one of two passed
    assert "PASS" in text and "FAIL" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_eval_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.report'`.

- [ ] **Step 3: Implement the report**

```python
# evals/report.py
"""Render an eval run as a markdown/plaintext summary."""

from __future__ import annotations


def _passed(case) -> bool:
    # duck-type: prefer an explicit .passed; else infer from assertions/scores
    if hasattr(case, "passed"):
        return bool(case.passed)
    assertions = getattr(case, "assertions", {}) or {}
    return all(getattr(a, "value", a) for a in assertions.values()) if assertions else False


def summarize(report) -> str:
    cases = list(report.cases)
    n = len(cases)
    passed = sum(1 for c in cases if _passed(c))
    lines = [f"# Eval result: {passed}/{n} passed", ""]
    total_tokens = total_latency = 0
    for c in cases:
        out = getattr(c, "output", None)
        tok = getattr(out, "tokens", 0) or 0
        lat = getattr(out, "latency_ms", 0) or 0
        total_tokens += tok
        total_latency += lat
        flag = "PASS" if _passed(c) else "FAIL"
        lines.append(f"- [{flag}] {c.name}  ({tok} tok, {lat} ms)")
    if n:
        lines += ["", f"avg tokens: {total_tokens // n} | avg latency: {total_latency // n} ms"]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the report test**

Run: `uv run pytest tests/unit/test_eval_report.py -v`
Expected: PASS.

- [ ] **Step 5: Implement the runner**

```python
# evals/run.py
"""Entry point: run an eval dataset against a pinned OpenAI model and print a summary.

Usage: RUN_EVAL=1 uv run python -m evals.run [--model gpt-5.4-mini] [--case <substr>]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from evals.datasets.google_free import build_google_free_dataset
from evals.models import build_eval_model
from evals.report import summarize


def main(model_alias: str = "gpt-5.4-mini", case_filter: str | None = None) -> int:
    if not os.environ.get("RUN_EVAL"):
        print("set RUN_EVAL=1 to run evals (real LLM, costs tokens)")
        return 0
    from app.core.config import settings
    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY not set — skipping")
        return 0

    from evals.harness import run_case

    model = build_eval_model(model_alias)
    dataset = build_google_free_dataset()
    if case_filter:
        dataset.cases = [c for c in dataset.cases if case_filter in c.name]

    async def task(inputs):
        return await run_case(inputs, model)

    report = dataset.evaluate_sync(task)
    print(summarize(report))
    # exit non-zero if any case failed (CI/regression gate)
    failed = sum(1 for c in report.cases if not getattr(c, "passed", True))
    return 1 if failed else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="gpt-5.4-mini")
    p.add_argument("--case", default=None)
    args = p.parse_args()
    sys.exit(main(args.model, args.case))
```

- [ ] **Step 6: Add make targets**

In `Makefile`, after the `sim:` target, add:

```makefile
eval-fast: ## Rodar os evals sem-Google (LLM real; usage: make eval-fast [MODEL=gpt-5.4-mini] [CASE=<substr>])
	@RUN_EVAL=1 $(UV) run python -m evals.run --model $(or $(MODEL),gpt-5.4-mini) $(if $(CASE),--case $(CASE),)

eval: ## Alias de eval-fast por enquanto (agenda/matriz vêm nas fases B/C)
	@make eval-fast MODEL=$(or $(MODEL),gpt-5.4-mini) CASE=$(CASE)
```

- [ ] **Step 7: Validate against the real LLM (Google-free)**

Run: `make eval-fast CASE=cliente_slot_filling`
Expected: the runner builds the dataset, pins `gpt-5.4-mini`, runs the slot-filling case against the real LLM, and prints a summary line `[PASS] cliente_slot_filling`. Then run the full Google-free set:
Run: `make eval-fast`
Expected: a summary with per-case PASS/FAIL, totals, avg tokens/latency. Record the baseline pass count in the commit message. (If `cliente_slot_filling` FAILS, that is a real signal — investigate the prompt, do not weaken the case.)

- [ ] **Step 8: Run the full unit suite + commit**

Run: `uv run pytest -q`
Expected: all green (eval unit tests included; eval real-LLM run is not part of the suite).

```bash
git add evals/report.py evals/run.py Makefile tests/unit/test_eval_report.py
git commit -m "feat(evals): runner + report + make eval-fast (google-free, single model)"
```

---

## Phase B & C — next plans (not in this plan)

These get their own plans once Phase A's harness shape is validated by a real `make eval-fast` run:

- **Phase B (agenda):** add a **persistent eval calendar** to the harness (create once, clear only events between cases — bounds Google calendar-creation quota) and apply the same fix to `tests/live/conftest.py`; add agenda cases A1–A8 (`create_event`, `create_recurring_event`, `list_events`, `cancel_event`, cancel-with-charge, `set_session_charge`, empty period, unknown client) with `DbState` event checks; a `make eval-agenda` target.
- **Phase C (matrix + judge):** add the built-in `pydantic_evals` `LLMJudge` evaluator (rubric for tone/slot-filling quality, judged by a fixed cheap model) to the conversational cases; run the dataset across the OpenAI matrix (`gpt-5.4-mini`, `gpt-5.4-nano`) with a comparison report (score/tokens/latency per model) and a regression diff against saved baselines (`evals/baselines/<model>.json`).
