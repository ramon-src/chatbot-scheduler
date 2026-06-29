"""billing_mode persists through create/update via the service."""

import uuid
from decimal import Decimal

import pytest

from app.core.database import SessionLocal
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate
from app.services.client_service import ClientService

DEV_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.mark.asyncio
async def test_create_and_update_billing_mode():
    db = SessionLocal()
    svc = ClientService(db)
    phone = "+5551900000123"
    try:
        created = await svc.create_client(ClientCreate(
            name="Bill Mode", phone=phone, user_id=DEV_USER_ID,
            invoice_day=10, consult_price=Decimal("200"), billing_mode="per_session"))
        row = db.query(Client).filter(Client.id == created.id).first()
        assert row.billing_mode == "per_session"
        await svc.update_client(created.id, DEV_USER_ID, ClientUpdate(billing_mode="monthly"))
        db.refresh(row)
        assert row.billing_mode == "monthly"
    finally:
        db.query(Client).filter(Client.phone == phone).delete(synchronize_session=False)
        db.commit()
        db.close()
