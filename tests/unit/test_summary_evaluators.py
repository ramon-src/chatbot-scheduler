"""Unit tests for the string-membership summary evaluators."""

from types import SimpleNamespace

from evals.evaluators import ExcludesAll, IncludesAll


def _ctx(output: str):
    return SimpleNamespace(output=output)


def test_excludes_all_true_when_no_token_present():
    assert ExcludesAll(tokens=["SQL", "select"]).evaluate(_ctx("Cliente Ana, 220 reais.")) is True


def test_excludes_all_false_when_any_token_present_case_insensitive():
    assert ExcludesAll(tokens=["SQL"]).evaluate(_ctx("ajuda com sql aqui")) is False


def test_includes_all_true_when_every_token_present():
    assert IncludesAll(tokens=["Ana", "250"]).evaluate(_ctx("Ana agora paga 250")) is True


def test_includes_all_false_when_a_token_missing():
    assert IncludesAll(tokens=["Ana", "250"]).evaluate(_ctx("Ana agora paga 200")) is False


def test_evaluators_tolerate_empty_output():
    assert ExcludesAll(tokens=["x"]).evaluate(_ctx("")) is True
    assert IncludesAll(tokens=["x"]).evaluate(_ctx("")) is False
