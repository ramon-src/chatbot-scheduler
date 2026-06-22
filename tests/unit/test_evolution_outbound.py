from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.channels.evolution_outbound import EvolutionOutboundAdapter
from app.channels.outbound import OutboundMessage


def _settings(**kw):
    base = dict(EVOLUTION_API_URL="https://evo.test", EVOLUTION_API_KEY="k", EVOLUTION_INSTANCE="inst")
    base.update(kw)
    return SimpleNamespace(**base)


def test_send_unconfigured_returns_false():
    adapter = EvolutionOutboundAdapter(_settings(EVOLUTION_API_URL=None))
    assert adapter.send(OutboundMessage(to_phone="5551999990000", text="oi")) is False


def test_send_posts_and_returns_true():
    adapter = EvolutionOutboundAdapter(_settings())
    with patch("app.channels.evolution_outbound.httpx.post") as post:
        post.return_value = MagicMock(status_code=201)
        ok = adapter.send(OutboundMessage(to_phone="5551999990000", text="olá"))
    assert ok is True
    url, kwargs = post.call_args[0][0], post.call_args[1]
    assert url == "https://evo.test/message/sendText/inst"
    assert kwargs["headers"]["apikey"] == "k"
    assert kwargs["json"]["number"] == "5551999990000"
    assert kwargs["json"]["text"] == "olá"


def test_send_swallows_errors_and_returns_false():
    adapter = EvolutionOutboundAdapter(_settings())
    with patch("app.channels.evolution_outbound.httpx.post", side_effect=RuntimeError("boom")):
        assert adapter.send(OutboundMessage(to_phone="5551999990000", text="x")) is False
