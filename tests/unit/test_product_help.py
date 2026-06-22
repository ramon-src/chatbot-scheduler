from app.agents.knowledge.product_faq import PRODUCT_SUMMARY, lookup


def test_lookup_no_topic_returns_summary():
    assert lookup() == PRODUCT_SUMMARY


def test_lookup_known_topic_returns_specific_guidance():
    msg = lookup("agenda")
    assert "recorrente" in msg.lower()


def test_lookup_unknown_topic_falls_back_to_summary():
    assert lookup("xpto-desconhecido") == PRODUCT_SUMMARY


def test_help_tool_registered_on_simplifica_agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    from app.agents.simplifica_agent import build_simplifica_agent

    agent = build_simplifica_agent()
    tool_names = set(agent._function_toolset.tools.keys())
    assert "product_help" in tool_names
