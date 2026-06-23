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
