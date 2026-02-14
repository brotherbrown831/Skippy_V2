#!/usr/bin/env python3
"""One-time OAuth2 consent flow for Gmail and Google Contacts.

Usage:
    pip install google-auth-oauthlib google-api-python-client
    python google_oauth.py

Expects google-oauth.json (client credentials) in the same directory.
Saves google-token.json to the same directory.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/contacts",
]

# Use the directory the script is in (works wherever you copy it)
SCRIPT_DIR = Path(__file__).parent
CLIENT_SECRETS = SCRIPT_DIR / "google-oauth.json"
TOKEN_FILE = SCRIPT_DIR / "google-token.json"


def main():
    if not CLIENT_SECRETS.exists():
        print(f"Error: Client credentials not found at {CLIENT_SECRETS}")
        print("Place google-oauth.json in the same folder as this script.")
        sys.exit(1)

    print("Starting OAuth2 consent flow...")
    print(f"Scopes: {', '.join(SCOPES)}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nToken saved to {TOKEN_FILE}")
    print("Now copy it to your dev machine:")
    print(f"  scp {TOKEN_FILE} nolan@10.0.10.132:/home/nolan/Skippy_V2/credentials/google-token.json")


if __name__ == "__main__":
    main()
