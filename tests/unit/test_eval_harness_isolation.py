from uuid import uuid4

from app.core.database import SessionLocal
from app.models.user import User
from evals.harness import EVAL_PHONE, EVAL_USER_ID, _ensure_eval_user, _purge


def test_purge_removes_lead_converted_user_so_pro_seed_does_not_collide():
    db = SessionLocal()
    try:
        _purge(db)
        # simulate a lead-converted user holding EVAL_PHONE under a different PK
        db.add(User(id=uuid4(), name="Lead Conv", email="lead-conv-isolation@simplificapsi.test", phone=EVAL_PHONE))
        db.commit()
        # purge must remove it...
        _purge(db)
        assert db.query(User).filter(User.phone == EVAL_PHONE).count() == 0
        # ...so the pro path can seed the eval user without an IntegrityError
        u = _ensure_eval_user(db)
        assert u.id == EVAL_USER_ID
    finally:
        _purge(db)
        # belt-and-suspenders cleanup of the stray email if anything remained
        db.query(User).filter(User.email == "lead-conv-isolation@simplificapsi.test").delete()
        db.commit()
        db.close()
