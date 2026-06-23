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
