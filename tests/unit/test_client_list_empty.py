# tests/unit/test_client_list_empty.py
from uuid import uuid4

from app.core.database import SessionLocal
from app.services.client_service import ClientService


async def test_list_clients_with_zero_clients_does_not_crash():
    """A professional with no clients must get an empty list, not a validation error
    (total_pages must be >= 1 even when total == 0)."""
    db = SessionLocal()
    try:
        res = await ClientService(db).list_clients(uuid4())  # user that has no clients
        assert res.total == 0
        assert res.total_pages == 1
        assert res.clients == []
    finally:
        db.close()
