from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services import calendar_provider
from app.services.calendar_provider import build_calendar_access


def _user(name="Dra. Ana", email="ana@gmail.com"):
    return SimpleNamespace(id=uuid4(), name=name, email=email)


def _settings():
    return SimpleNamespace(TIMEZONE="America/Sao_Paulo",
                           GOOGLE_CLIENT_EMAIL="sa@x.iam", GOOGLE_PRIVATE_KEY="k")


def _es(existing=None):
    es = MagicMock()
    es.get_existing_primary.return_value = existing
    es.ensure_calendar.side_effect = lambda uid, gcid, name="Principal": SimpleNamespace(
        id=uuid4(), user_id=uid, google_calendar_id=gcid, name=name, is_primary=True
    )
    return es


def test_oauth_takes_priority(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: True)
    monkeypatch.setattr(calendar_provider, "load_credentials", lambda db, uid: MagicMock())
    es = _es()
    access = build_calendar_access(
        MagicMock(), _user(), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    assert access.calendar.google_calendar_id == "primary"
    es.ensure_calendar.assert_called_once()
    assert es.ensure_calendar.call_args.args[1] == "primary"  # ensure_calendar(user_id, "primary")


def test_sa_default_creates_and_shares_calendar(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    fake_sa_creds = object()
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: fake_sa_creds)

    created_service = MagicMock()
    created_service.create_calendar.return_value = {"id": "sa-cal@group.calendar.google.com"}
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService",
                        lambda resource, tz, calendar_id=None: created_service)

    es = _es(existing=None)
    access = build_calendar_access(
        MagicMock(), _user(email="ana@gmail.com"), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    created_service.create_calendar.assert_called_once()
    created_service.share_calendar.assert_called_once_with("sa-cal@group.calendar.google.com", "ana@gmail.com")
    es.ensure_calendar.assert_called_once()
    assert es.ensure_calendar.call_args.args[1] == "sa-cal@group.calendar.google.com"


def test_sa_reuses_existing_calendar(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: object())
    svc = MagicMock()
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService",
                        lambda resource, tz, calendar_id=None: svc)
    existing = SimpleNamespace(id=uuid4(), google_calendar_id="old-cal@group.calendar.google.com", is_primary=True)
    es = _es(existing=existing)
    access = build_calendar_access(
        MagicMock(), _user(), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    svc.create_calendar.assert_not_called()  # reused, not recreated


def test_share_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: object())
    svc = MagicMock()
    svc.create_calendar.return_value = {"id": "sa-cal"}
    svc.share_calendar.side_effect = RuntimeError("not a google account")
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService",
                        lambda resource, tz, calendar_id=None: svc)
    es = _es(existing=None)
    access = build_calendar_access(
        MagicMock(), _user(email="x@x.com"), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None  # share failure does not break scheduling


def test_no_credentials_and_no_sa_returns_none(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: None)
    access = build_calendar_access(
        MagicMock(), _user(), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=_es(),
    )
    assert access is None


def test_no_share_when_user_has_no_email(monkeypatch):
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: False)
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", lambda s: object())
    svc = MagicMock()
    svc.create_calendar.return_value = {"id": "sa-cal"}
    monkeypatch.setattr(calendar_provider, "GoogleCalendarService",
                        lambda resource, tz, calendar_id=None: svc)
    es = _es(existing=None)
    access = build_calendar_access(
        MagicMock(), _user(email=None), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=es,
    )
    assert access is not None
    svc.share_calendar.assert_not_called()


def test_broken_oauth_does_not_fall_back_to_sa(monkeypatch):
    """An OAuth user whose token load fails must return None, NOT silently use the SA
    (would split their events across calendars)."""
    monkeypatch.setattr(calendar_provider, "has_credentials", lambda db, uid: True)

    def _boom(db, uid):
        raise RuntimeError("token revoked")

    monkeypatch.setattr(calendar_provider, "load_credentials", _boom)
    sa_spy = MagicMock(return_value=object())
    monkeypatch.setattr(calendar_provider, "build_service_account_credentials", sa_spy)
    access = build_calendar_access(
        MagicMock(), _user(), _settings(),
        build_resource=lambda creds: MagicMock(), event_service=_es(),
    )
    assert access is None
    sa_spy.assert_not_called()  # did not fall back to service account
