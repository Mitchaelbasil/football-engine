"""One-time Google OAuth login for football-engine.

Opens a browser for consent and saves the resulting credentials to
token.json (gitignored). Never prints secret values.

Usage:
    python scripts/google_auth.py [--client-secret client_secret.json] [--token token.json]
"""

import argparse
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client-secret", default=ROOT / "client_secret.json", type=Path)
    parser.add_argument("--token", default=ROOT / "token.json", type=Path)
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(str(args.client_secret), SCOPES)
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        open_browser=True,
    )

    if not creds.refresh_token:
        raise SystemExit("No refresh token returned; revoke the app's access and retry.")

    args.token.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(args.token, 0o600)
    except OSError:
        pass
    print(f"Login succeeded. Credentials saved to {args.token.name} (not printed).")


if __name__ == "__main__":
    main()
