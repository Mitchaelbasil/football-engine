"""Google API clients built from the refresh token stored in GitHub Secrets.

Env vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.
Scopes come from the refresh token itself (see scripts/google_auth.py).
"""

import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_URI = "https://oauth2.googleapis.com/token"

_creds = None


def credentials() -> Credentials:
    global _creds
    if _creds is None:
        _creds = Credentials(
            None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            token_uri=TOKEN_URI,
        )
    return _creds


def build_service(name: str, version: str):
    return build(name, version, credentials=credentials(), cache_discovery=False)
