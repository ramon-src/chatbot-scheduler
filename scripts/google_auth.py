"""One-time interactive OAuth consent for a user's Google Calendar.

Prereqs: a Google Cloud OAuth *Desktop* client. Put its values in .env:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
Run:  uv run python scripts/google_auth.py [USER_UUID]
Default USER_UUID is the dev user. Opens a browser; on success stores the
refresh token in simplificapsi.google_credentials.
"""

import sys
from uuid import UUID

from google_auth_oauthlib.flow import InstalledAppFlow

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.google_auth import store_credentials

DEV_USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


def main() -> None:
    user_id = UUID(sys.argv[1]) if len(sys.argv) > 1 else DEV_USER_ID
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise SystemExit("Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env primeiro.")

    client_config = {
        "installed": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=settings.GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    db = SessionLocal()
    try:
        store_credentials(db, user_id, creds)
    finally:
        db.close()
    print(f"Google Agenda conectada para o usuário {user_id}.")


if __name__ == "__main__":
    main()
