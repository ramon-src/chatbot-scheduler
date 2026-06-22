from app.models.inbound_message import InboundMessageRecord


def test_table_and_columns():
    t = InboundMessageRecord.__table__
    assert t.schema == "simplificapsi"
    assert t.name == "inbound_message"
    cols = set(t.columns.keys())
    assert {
        "id", "provider", "provider_message_id", "sender_phone",
        "recipient_phone", "text", "classification", "user_id", "raw", "received_at",
    } <= cols
    uniques = [
        tuple(sorted(c.name for c in con.columns))
        for con in t.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("provider", "provider_message_id") in uniques


def test_exported_from_models_package():
    from app.models import InboundMessageRecord as Exported
    assert Exported is InboundMessageRecord


def test_raw_column_is_jsonb():
    from sqlalchemy.dialects.postgresql import JSONB
    col = InboundMessageRecord.__table__.columns["raw"]
    assert isinstance(col.type, JSONB)
