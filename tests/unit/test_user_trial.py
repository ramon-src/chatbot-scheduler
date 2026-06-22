from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User


def test_user_has_access_expires_at_column():
    db = SessionLocal()
    try:
        expires = datetime.now(ZoneInfo(settings.TIMEZONE)) + timedelta(days=7)
        u = User(name="Trial User", email="trial-col-test@simplificapsi.test", access_expires_at=expires)
        db.add(u)
        db.commit()
        db.refresh(u)
        assert u.access_expires_at is not None
    finally:
        db.query(User).filter(User.email == "trial-col-test@simplificapsi.test").delete()
        db.commit()
        db.close()


def test_lead_trial_days_default():
    assert settings.LEAD_TRIAL_DAYS == 7
