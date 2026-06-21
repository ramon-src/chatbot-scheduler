# tests/unit/test_agent_agenda_wiring.py
from app.agents.simplifica_agent import build_simplifica_agent


def test_agent_registers_calendar_tools(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    agent = build_simplifica_agent()
    tool_names = set(agent._function_toolset.tools.keys())  # pydantic-ai tool registry
    for name in ("create_event", "create_recurring_event", "list_events", "cancel_event"):
        assert name in tool_names, f"{name} not registered (have: {tool_names})"
