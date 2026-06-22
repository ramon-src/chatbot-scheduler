from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services import agent_runner


def test_route_uses_calendar_provider(monkeypatch):
    """The route must resolve calendar access via build_calendar_access and use its service."""
    sentinel_service = object()
    user = SimpleNamespace(id=uuid4(), name="Dra. Ana", email="ana@gmail.com")
    monkeypatch.setattr(agent_runner, "build_calendar_access",
                        lambda db, u, s: SimpleNamespace(service=sentinel_service, calendar=None))
    deps = agent_runner.build_agent_deps(db=MagicMock(), user=user, history_summary="resumo aqui")
    assert deps.calendar_service is sentinel_service
    assert deps.user_name == "Dra. Ana"
    assert deps.user_id == user.id
    assert deps.history_summary == "resumo aqui"


def test_route_handles_no_calendar_access(monkeypatch):
    user = SimpleNamespace(id=uuid4(), name="Dr. Bob", email=None)
    monkeypatch.setattr(agent_runner, "build_calendar_access", lambda db, u, s: None)
    deps = agent_runner.build_agent_deps(db=MagicMock(), user=user, history_summary=None)
    assert deps.calendar_service is None
    assert deps.user_name == "Dr. Bob"


def test_route_swallows_provider_exception(monkeypatch):
    """A provider blow-up must never propagate (would 500 the chat) — degrade to no calendar."""
    user = SimpleNamespace(id=uuid4(), name="Dr. C", email=None)

    def _boom(db, u, s):
        raise RuntimeError("google down")

    monkeypatch.setattr(agent_runner, "build_calendar_access", _boom)
    deps = agent_runner.build_agent_deps(db=MagicMock(), user=user, history_summary=None)
    assert deps.calendar_service is None
