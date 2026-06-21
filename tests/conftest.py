import pytest
import pydantic_ai.models


@pytest.fixture(autouse=True)
def _block_real_model_requests(monkeypatch):
    monkeypatch.setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", False)
