"""Idempotent dev seed: ensures a fixed development user exists.

Usage:
    uv run python scripts/seed_dev.py

The fixed user_id matches scripts/init-db.sql so the agent endpoint can be
exercised right away:
    550e8400-e29b-41d4-a716-446655440000
"""

from uuid import UUID

from app.core.database import SessionLocal
from app.models.user import User

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
DEV_USER_EMAIL = "dev@simplificapsi.com"
DEV_USER_NAME = "Dev Psicologo"
DEV_USER_PHONE = "+5551981321543"


def seed_dev_user() -> None:
    db = SessionLocal()
    try:
        existing = db.get(User, DEV_USER_ID)
        if existing:
            print(f"✅ Dev user already present: {DEV_USER_ID}")
            return

        user = User(
            id=DEV_USER_ID,
            email=DEV_USER_EMAIL,
            name=DEV_USER_NAME,
            phone=DEV_USER_PHONE,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"✅ Dev user created: {DEV_USER_ID} ({DEV_USER_EMAIL})")
    except Exception as exc:  # pragma: no cover - dev convenience script
        db.rollback()
        raise SystemExit(f"❌ Failed to seed dev user: {exc}") from exc
    finally:
        db.close()


if __name__ == "__main__":
    seed_dev_user()
