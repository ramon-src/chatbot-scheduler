"""Entry point: run an eval dataset against a pinned OpenAI model and print a summary.

Usage: RUN_EVAL=1 uv run python -m evals.run [--model gpt-5.4-mini] [--case <substr>]
"""

from __future__ import annotations

import argparse
import os
import sys

from evals.datasets.google_free import build_google_free_dataset
from evals.models import build_eval_model
from evals.report import summarize


def main(model_alias: str = "gpt-5.4-mini", case_filter: str | None = None, suite: str = "agent") -> int:
    if not os.environ.get("RUN_EVAL"):
        print("set RUN_EVAL=1 to run evals (real LLM, costs tokens)")
        return 0
    from app.core.config import settings
    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY not set — skipping")
        return 0

    model = build_eval_model(model_alias)

    if suite == "summary":
        from evals.datasets.summary_cleaning import build_summary_cleaning_dataset
        from evals.harness import run_summary_case

        dataset = build_summary_cleaning_dataset()

        async def task(inputs):
            return await run_summary_case(inputs, model)
    elif suite == "agenda":
        from evals.datasets.agenda import build_agenda_dataset
        from evals.harness import run_case

        dataset = build_agenda_dataset()

        async def task(inputs):
            return await run_case(inputs, model)
    else:
        from evals.harness import run_case

        dataset = build_google_free_dataset()

        async def task(inputs):
            return await run_case(inputs, model)

    if case_filter:
        dataset.cases = [c for c in dataset.cases if case_filter in c.name]

    report = dataset.evaluate_sync(task, max_concurrency=1)
    print(summarize(report))
    # exit non-zero if any case failed or errored (CI/regression gate)
    failed = sum(1 for c in report.cases if not _case_passed(c))
    errored = len(getattr(report, "failures", []) or [])
    return 1 if (failed + errored) else 0


def _case_passed(case) -> bool:
    """Duck-typed pass check — mirrors evals.report._passed but inline for runner."""
    if hasattr(case, "passed"):
        return bool(case.passed)
    assertions = getattr(case, "assertions", {}) or {}
    return all(getattr(a, "value", a) for a in assertions.values()) if assertions else False


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="gpt-5.4-mini")
    p.add_argument("--case", default=None)
    p.add_argument("--suite", default="agent", choices=["agent", "summary", "agenda"])
    args = p.parse_args()
    sys.exit(main(args.model, args.case, args.suite))
