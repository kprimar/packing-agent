"""
Gmail API email sender using OAuth2 — no password stored.

First run opens a browser for Google sign-in and saves a token to
credentials/gmail_token.json. Subsequent runs refresh the token silently.

Setup:
  1. Copy credentials.json from your calendar-agent project into
     this project's credentials/ folder.
  2. Run: python daily_outfit.py  (browser opens once for sign-in)
"""

import base64
import email as emaillib
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
_CREDS_DIR = Path(__file__).parent.parent / "credentials"
_CREDS_FILE = _CREDS_DIR / "credentials.json"
_TOKEN_FILE = _CREDS_DIR / "gmail_token.json"


def _get_service():
    if not _CREDS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {_CREDS_FILE}\n"
            "Copy it from your calendar-agent/credentials/ folder."
        )

    _CREDS_DIR.mkdir(parents=True, exist_ok=True)
    creds = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Opening browser for Google sign-in (one-time only)…")
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS_FILE), _SCOPES)
            creds = flow.run_local_server(port=0)
        _TOKEN_FILE.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_email(subject: str, body: str, to_email: str):
    service = _get_service()

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["To"] = to_email

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
