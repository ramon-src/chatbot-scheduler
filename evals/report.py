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
    # Include harness-level failures (e.g. PendingRollbackError between cases)
    failures = list(getattr(report, "failures", []) or [])
    all_items = cases + failures
    n = len(all_items)
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
    for f in failures:
        err = getattr(f, "error_message", "harness error") or "harness error"
        lines.append(f"- [ERROR] {f.name}  ({err[:80]})")
    if n:
        lines += ["", f"avg tokens: {total_tokens // n} | avg latency: {total_latency // n} ms"]
    return "\n".join(lines)
