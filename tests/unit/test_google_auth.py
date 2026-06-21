from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services import google_auth
from app.services.google_auth import GoogleAuthError, has_credentials, load_credentials


def _fake_row(**over):
    base = dict(
        refresh_token="rt", token="at", token_uri="https://oauth2.googleapis.com/token",
        client_id="cid", client_secret="secret", scopes="https://www.googleapis.com/auth/calendar",
        expiry=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _db_returning(row):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    return db


def test_no_credential_raises(monkeypatch):
    db = _db_returning(None)
    with pytest.raises(GoogleAuthError):
        load_credentials(db, uuid4())


def test_has_credentials_false_when_missing():
    assert has_credentials(_db_returning(None), uuid4()) is False


def test_has_credentials_true_when_present():
    assert has_credentials(_db_returning(_fake_row()), uuid4()) is True


def test_load_builds_credentials_without_refresh_when_valid(monkeypatch):
    captured = {}

    class FakeCreds:
        def __init__(self, token=None, **kw):
            captured.update(kw, token=token)
            self.token = token
            self.expired = False
            self.valid = True

        def refresh(self, request):  # should not be called
            captured["refreshed"] = True

    monkeypatch.setattr(google_auth, "Credentials", FakeCreds)
    creds = load_credentials(_db_returning(_fake_row()), uuid4())
    assert isinstance(creds, FakeCreds)
    assert captured["refresh_token"] == "rt"
    assert "refreshed" not in captured


def test_load_refreshes_and_persists_when_expired(monkeypatch):
    class FakeCreds:
        def __init__(self, token=None, **kw):
            self.token = token
            self.expired = True
            self.valid = False
            self.expiry = None

        def refresh(self, request):
            self.token = "new-access-token"
            self.expired = False
            self.valid = True
            self.expiry = "2026-12-31T00:00:00"

    monkeypatch.setattr(google_auth, "Credentials", FakeCreds)
    monkeypatch.setattr(google_auth, "Request", lambda: object())
    row = _fake_row()
    db = _db_returning(row)
    creds = load_credentials(db, uuid4())
    assert creds.token == "new-access-token"
    assert row.token == "new-access-token"  # persisted back to the row
    assert row.expiry == "2026-12-31T00:00:00"  # expiry persisted too
    db.commit.assert_called_once()


def test_load_wraps_refresh_failure_as_domain_error(monkeypatch):
    """A google refresh exception must surface as GoogleAuthError, never leak raw."""
    class FakeCreds:
        def __init__(self, token=None, **kw):
            self.token = token
            self.expired = True
            self.valid = False

        def refresh(self, request):
            raise RuntimeError("invalid_grant: token revoked")

    monkeypatch.setattr(google_auth, "Credentials", FakeCreds)
    monkeypatch.setattr(google_auth, "Request", lambda: object())
    db = _db_returning(_fake_row())
    with pytest.raises(GoogleAuthError):
        load_credentials(db, uuid4())
    db.commit.assert_not_called()
