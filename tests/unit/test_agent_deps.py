# tests/unit/test_agent_deps.py
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock
from app.agents.deps import AgentDeps


def test_agent_deps_holds_context():
    deps = AgentDeps(
        db=MagicMock(),
        user_id=uuid4(),
        user_name="Ramon",
        current_datetime=datetime(2026, 6, 21, 15, 0),
        timezone="America/Sao_Paulo",
        history_summary=None,
        client_service=MagicMock(),
    )
    assert deps.user_name == "Ramon"
    assert deps.timezone == "America/Sao_Paulo"
