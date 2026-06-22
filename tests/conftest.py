import pydantic_ai.models
import pytest


@pytest.fixture(autouse=True)
def _block_real_model_requests(request, monkeypatch):
    # Live functional tests intentionally use the real LLM — don't block them.
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", False)
