"""The eval harness can seed a calendar + events and snapshot them with client/time."""

from evals.harness import (
    EVAL_USER_ID, CaseInputs, _apply_setup, _ensure_eval_user, _purge, _snapshot,
)
from app.core.database import SessionLocal


def test_apply_setup_seeds_events_and_snapshot_reports_them():
    db = SessionLocal()
    try:
        _purge(db)
        _ensure_eval_user(db)
        inputs = CaseInputs(agent="pro", messages=[], setup={
            "clients": [{"name": "Maria Silva", "phone": "+5551999990000",
                         "invoice_day": 10, "consult_price": 200}],
            "events": [{"client": "Maria Silva", "start": "2026-06-24T10:00:00-03:00",
                        "duration": 60}],
        })
        _apply_setup(db, inputs)
        snap = _snapshot(db, inputs)
        assert any(e.get("client") and "Maria" in e["client"] for e in snap.events)
        assert any("2026-06-24" in (e.get("start_time") or "") for e in snap.events)
    finally:
        _purge(db)
        db.close()
