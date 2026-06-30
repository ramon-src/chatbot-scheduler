"""ClientCreate/Update accept and validate billing_mode."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.client import ClientCreate, ClientUpdate


def _base(**over):
    data = dict(name="Maria Silva", phone="+5551999990000", user_id=uuid.uuid4(),
                invoice_day=10, consult_price=Decimal("200"))
    data.update(over)
    return data


def test_create_defaults_to_monthly():
    c = ClientCreate(**_base())
    assert c.billing_mode == "monthly"


def test_create_accepts_per_session():
    c = ClientCreate(**_base(billing_mode="per_session"))
    assert c.billing_mode == "per_session"


def test_create_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        ClientCreate(**_base(billing_mode="weekly"))


def test_update_billing_mode_optional_and_validated():
    assert ClientUpdate().billing_mode is None
    assert ClientUpdate(billing_mode="monthly").billing_mode == "monthly"
    with pytest.raises(ValidationError):
        ClientUpdate(billing_mode="bogus")
