from evals.datasets.google_free import build_google_free_dataset
from evals.harness import CaseInputs


def test_dataset_builds_with_expected_cases():
    ds = build_google_free_dataset()
    names = {c.name for c in ds.cases}
    # key cases exist, including the slot-filling regression
    assert "cliente_criar_uma_msg" in names
    assert "cliente_slot_filling" in names
    assert "cliente_homonimo_pede_telefone" in names
    assert "lead_cria_conta" in names
    # all inputs are CaseInputs and the slot-filling case is multi-turn
    sf = next(c for c in ds.cases if c.name == "cliente_slot_filling")
    assert isinstance(sf.inputs, CaseInputs)
    assert len(sf.inputs.messages) >= 4  # fragmented across messages
    assert sf.evaluators  # has evaluators attached
