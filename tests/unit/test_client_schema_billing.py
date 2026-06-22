from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from app.schemas.client import ClientCreate, ClientResponse

def test_client_create_requires_billing_fields():
    c = ClientCreate(
        name="Maria Silva",
        phone="+5551981321543",
        user_id=uuid4(),
        invoice_day=10,
        consult_price=Decimal("200.00"),
    )
    assert c.invoice_day == 10
    assert c.consult_price == Decimal("200.00")


def test_client_response_accepts_datetime_timestamps():
    """Regression: ORM columns are DateTime, so created_at/updated_at must accept
    datetime (with time), not only date. Previously typed as `date`, which raised
    date_from_datetime_inexact and broke every client read path."""
    r = ClientResponse(
        id=uuid4(),
        user_id=uuid4(),
        name="Maria Silva",
        phone="+5551981321543",
        created_at=datetime(2026, 6, 21, 19, 30, 5),
        updated_at=datetime(2026, 6, 21, 19, 31, 0),
    )
    assert r.created_at.hour == 19
    assert r.updated_at.minute == 31


def test_client_response_from_orm_carries_billing_fields():
    """Regression: ClientResponse.from_orm passes invoice_day/consult_price, but the
    schema must DECLARE them or Pydantic drops them — which broke price stamping in
    create_event (AttributeError on client.consult_price). Proven via a stub ORM."""
    from types import SimpleNamespace

    orm = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), name="Maria Silva", phone="+5551981321543",
        email=None, birth_date=None, notes=None, is_active=True,
        invoice_day=10, consult_price=Decimal("200.00"),
        created_at=datetime(2026, 6, 21, 19, 30, 5),
        updated_at=datetime(2026, 6, 21, 19, 31, 0),
    )
    r = ClientResponse.from_orm(orm)
    assert r.consult_price == Decimal("200.00")
    assert r.invoice_day == 10
