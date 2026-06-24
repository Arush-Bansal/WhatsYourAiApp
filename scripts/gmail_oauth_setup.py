#!/usr/bin/env python3
"""One-time OAuth setup to obtain a Gmail refresh token for GMAIL_REFRESH_TOKEN."""

from __future__ import annotations

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main() -> None:
    client_id = os.environ.get("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in your environment first.")
        raise SystemExit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nAdd these to your .env:\n")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    if creds.token:
        print(f"# Access token (expires; refresh token above is what you need): {creds.token[:20]}...")


if __name__ == "__main__":
    main()
