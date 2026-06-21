from decimal import Decimal
from uuid import uuid4
from app.schemas.client import ClientCreate

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
