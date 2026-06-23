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
