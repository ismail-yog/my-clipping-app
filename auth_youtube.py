"""
StreamClipper — YouTube One-Time Auth Setup
===========================================
Run this script ONCE to authorize YouTube access.
The token is saved and auto-refreshed forever — no repeat login needed.

Usage:
    python auth_youtube.py
"""

import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SECRETS_FILE = Path("client_secrets.json")
TOKEN_FILE   = Path("youtube_token.json")
SCOPES       = ["https://www.googleapis.com/auth/youtube.upload"]


def check_existing_token():
    """Return valid creds if token exists and is usable, else None."""
    if not TOKEN_FILE.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if creds.valid:
            logger.info("Token is already valid.")
            return creds

        if creds.expired and creds.refresh_token:
            logger.info("Token expired — refreshing...")
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
            logger.info("Token refreshed successfully.")
            return creds

        if not creds.refresh_token:
            logger.warning(
                "Token exists but has no refresh_token — need to re-authorize.\n"
                "If this keeps happening, revoke the app at:\n"
                "  https://myaccount.google.com/permissions\n"
                "Then run this script again."
            )
            return None

    except Exception as e:
        logger.warning("Could not load existing token: %s", e)
    return None


def run_auth_flow():
    """
    Opens the system browser for Google sign-in.
    run_local_server() handles everything automatically:
      - Picks a free port
      - Opens browser
      - Waits for callback
      - Returns credentials with refresh_token
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    logger.info("Opening browser for Google sign-in...")
    flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)

    creds = flow.run_local_server(
        port=8080,            # Fixed port — must have http://localhost:8080 in Google Cloud Console
        access_type="offline",
        prompt="consent",     # Force consent so refresh_token is always issued
        open_browser=True,
    )

    return creds


def main():
    print("=" * 54)
    print("  StreamClipper - YouTube Authorization Setup")
    print("=" * 54)

    if not SECRETS_FILE.exists():
        print(f"\n[ERROR] {SECRETS_FILE} not found.")
        print("    Download it from:")
        print("    Google Cloud Console > APIs & Services > Credentials")
        print("    > OAuth 2.0 Client IDs > Download JSON")
        sys.exit(1)

    creds = check_existing_token()
    if creds:
        print(f"\n[OK] Already authorized - token is valid.")
        print(f"     File: {TOKEN_FILE.resolve()}")
        print("     No action needed. StreamClipper is ready to upload.")
        return

    try:
        creds = run_auth_flow()
    except Exception as e:
        print(f"\n[ERROR] Authorization failed: {e}")
        print("\n    Common fixes:")
        print("    1. Make sure http://localhost:8080 is in your OAuth redirect URIs")
        print("       (Google Cloud Console > Credentials > Edit > Authorized redirect URIs)")
        print("    2. Revoke the app at https://myaccount.google.com/permissions and retry")
        sys.exit(1)

    if not creds.refresh_token:
        print("\n[WARNING] No refresh_token received from Google.")
        print("    Fix: Go to https://myaccount.google.com/permissions")
        print("    Revoke access for this app, then run this script again.")
    else:
        print("\n[OK] Got refresh_token - login will persist permanently.")

    TOKEN_FILE.write_text(creds.to_json())
    print(f"\n[OK] Token saved to: {TOKEN_FILE.resolve()}")
    print("     StreamClipper will auto-refresh the token - no re-login needed.")


if __name__ == "__main__":
    main()
