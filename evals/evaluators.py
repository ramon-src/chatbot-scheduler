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
        if "event_for_client" in c:
            name = c["event_for_client"]
            if not any(
                (ev.get("client") or "") and name in ev["client"] and ev.get("status") != "cancelled"
                for ev in db.events
            ):
                return False
        return True


@dataclass
class ExcludesAll(Evaluator):
    """Pass when NONE of the tokens appear in the string output (case-insensitive)."""

    tokens: list[str]

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        text = (ctx.output or "").lower()
        return all(t.lower() not in text for t in self.tokens)


@dataclass
class IncludesAll(Evaluator):
    """Pass when EVERY token appears in the string output (case-insensitive)."""

    tokens: list[str]

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        text = (ctx.output or "").lower()
        return all(t.lower() in text for t in self.tokens)
