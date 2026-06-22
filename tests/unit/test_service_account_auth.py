from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import google_auth
from app.services.google_auth import build_service_account_credentials, service_account_available


def _settings(email="sa@x.iam.gserviceaccount.com", key="-----BEGIN-----\\nabc\\n-----END-----"):
    return SimpleNamespace(GOOGLE_CLIENT_EMAIL=email, GOOGLE_PRIVATE_KEY=key)


def test_available_true_when_both_set():
    assert service_account_available(_settings()) is True


def test_available_false_when_missing():
    assert service_account_available(_settings(email=None)) is False
    assert service_account_available(_settings(key=None)) is False


def test_build_returns_none_when_unavailable():
    assert build_service_account_credentials(_settings(email="")) is None


def test_build_unescapes_newlines_and_sets_scope(monkeypatch):
    captured = {}

    class FakeSA:
        class Credentials:
            @staticmethod
            def from_service_account_info(info, scopes=None):
                captured["info"] = info
                captured["scopes"] = scopes
                return MagicMock(name="sa-credentials")

    monkeypatch.setattr(google_auth, "service_account", FakeSA)
    creds = build_service_account_credentials(_settings())
    assert creds is not None
    assert captured["info"]["client_email"] == "sa@x.iam.gserviceaccount.com"
    assert "\\n" not in captured["info"]["private_key"]  # un-escaped to real newlines
    assert "\n" in captured["info"]["private_key"]
    assert captured["scopes"] == ["https://www.googleapis.com/auth/calendar"]
    assert captured["info"]["token_uri"] == "https://oauth2.googleapis.com/token"
