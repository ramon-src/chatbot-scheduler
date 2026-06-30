from types import SimpleNamespace

from evals.report import summarize


def _case(name, passed, tokens, latency):
    out = SimpleNamespace(tokens=tokens, latency_ms=latency)
    return SimpleNamespace(name=name, passed=passed, output=out)


def test_summarize_reports_totals_and_per_case():
    report = SimpleNamespace(cases=[
        _case("cliente_slot_filling", True, 1200, 3000),
        _case("cliente_telefone_duplicado", False, 800, 2000),
    ])
    text = summarize(report)
    assert "cliente_slot_filling" in text
    assert "1/2" in text or "1 / 2" in text  # one of two passed
    assert "PASS" in text and "FAIL" in text
