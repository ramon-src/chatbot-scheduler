"""Unit tests for GoogleCredential model."""

from app.models import GoogleCredential
from app.models.google_credential import GoogleCredential as Direct


def test_model_table_and_schema():
    assert GoogleCredential is Direct
    assert GoogleCredential.__tablename__ == "google_credentials"
    assert GoogleCredential.__table_args__["schema"] == "simplificapsi"


def test_model_has_oauth_columns():
    cols = GoogleCredential.__table__.columns
    for name in ("user_id", "refresh_token", "token", "token_uri", "client_id", "client_secret", "scopes", "expiry"):
        assert name in cols, f"missing column {name}"
    assert cols["user_id"].unique is True
    assert cols["refresh_token"].nullable is False
