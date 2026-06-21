"""Build/refresh google OAuth credentials from the per-user DB row."""

from uuid import UUID

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.models.google_credential import GoogleCredential


class GoogleAuthError(Exception):
    """User has not connected Google Calendar, or token refresh failed."""


def _get_row(db: Session, user_id: UUID) -> GoogleCredential | None:
    return db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()


def has_credentials(db: Session, user_id: UUID) -> bool:
    return _get_row(db, user_id) is not None


def load_credentials(db: Session, user_id: UUID) -> Credentials:
    row = _get_row(db, user_id)
    if row is None:
        raise GoogleAuthError("Usuário não conectou a Google Agenda.")

    creds = Credentials(
        token=row.token,
        refresh_token=row.refresh_token,
        token_uri=row.token_uri,
        client_id=row.client_id,
        client_secret=row.client_secret,
        scopes=row.scopes.split(),
    )

    if getattr(creds, "expired", False) or not getattr(creds, "valid", True):
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001 - surface as domain error
            raise GoogleAuthError(f"Falha ao renovar o acesso à Google Agenda: {exc}") from exc
        row.token = creds.token
        row.expiry = getattr(creds, "expiry", None)
        db.commit()

    return creds


def store_credentials(db: Session, user_id: UUID, creds: Credentials) -> None:
    """Upsert the DB row from a Credentials object (used by the consent CLI)."""
    row = _get_row(db, user_id)
    scopes = " ".join(creds.scopes or [])
    if row is None:
        row = GoogleCredential(user_id=user_id)
        db.add(row)
    row.refresh_token = creds.refresh_token
    row.token = creds.token
    row.token_uri = creds.token_uri
    row.client_id = creds.client_id
    row.client_secret = creds.client_secret
    row.scopes = scopes
    row.expiry = getattr(creds, "expiry", None)
    db.commit()
