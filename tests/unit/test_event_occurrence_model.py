# tests/unit/test_event_occurrence_model.py
from app.models.event import Event


def test_occurrence_columns_exist():
    cols = Event.__table__.columns
    assert "parent_event_id" in cols
    assert "occurrence_date" in cols
    assert "billable" in cols


def test_unique_occurrence_constraint():
    uniques = [
        tuple(sorted(c.name for c in con.columns))
        for con in Event.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("occurrence_date", "parent_event_id") in uniques
