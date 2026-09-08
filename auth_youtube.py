"""
StreamClipper — YouTube One-Time Auth Setup
===========================================
Run this script ONCE to authorize YouTube access.
The token is saved and auto-refreshed forever — no repeat login needed.

Usage:
    python auth_youtube.py
"""

import argparse
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def check_existing_token(token_file: Path):
    """Return valid creds if token exists and is usable, else None."""
    if not token_file.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

        if creds.valid:
            logger.info("Token is already valid.")
            return creds

        if creds.expired and creds.refresh_token:
            logger.info("Token expired — refreshing...")
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
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


def run_auth_flow(secrets_file: Path, port: int = 8080):
    """
    Opens the system browser for Google sign-in.
    run_local_server() handles everything automatically:
      - Picks or binds port
      - Opens browser
      - Waits for callback
      - Returns credentials with refresh_token
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    logger.info("Opening browser for Google sign-in...")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)

    creds = flow.run_local_server(
        port=port,
        access_type="offline",
        prompt="consent",
        open_browser=True,
    )

    return creds


def main():
    parser = argparse.ArgumentParser(
        description="StreamClipper YouTube OAuth Setup (Multi-Account Supported)"
    )
    parser.add_argument(
        "--secrets",
        type=str,
        default="client_secrets.json",
        help="Path to client_secrets JSON file (default: client_secrets.json)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default="youtube_token.json",
        help="Path to save output token JSON (default: youtube_token.json)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Callback server port (default: 8080)",
    )
    args = parser.parse_args()

    secrets_file = Path(args.secrets)
    token_file = Path(args.token)

    print("=" * 54)
    print("  StreamClipper - YouTube Authorization Setup")
    print("=" * 54)
    print(f"  Secrets File : {secrets_file}")
    print(f"  Token Output : {token_file}")
    print(f"  Local Port   : {args.port}")
    print("=" * 54)

    if not secrets_file.exists():
        print(f"\n[ERROR] {secrets_file} not found.")
        print("    Download it from:")
        print("    Google Cloud Console > APIs & Services > Credentials")
        print("    > OAuth 2.0 Client IDs > Download JSON")
        sys.exit(1)

    creds = check_existing_token(token_file)
    if creds:
        print(f"\n[OK] Already authorized - token is valid.")
        print(f"     File: {token_file.resolve()}")
        print("     No action needed. Ready to upload.")
        return

    try:
        creds = run_auth_flow(secrets_file, port=args.port)
    except Exception as e:
        print(f"\n[ERROR] Authorization failed: {e}")
        print("\n    Common fixes:")
        print(f"    1. Make sure http://localhost:{args.port} or http://localhost:{args.port}/ is in your OAuth redirect URIs")
        print("       (Google Cloud Console > Credentials > Edit > Authorized redirect URIs)")
        print("    2. Revoke the app at https://myaccount.google.com/permissions and retry")
        sys.exit(1)

    if not creds.refresh_token:
        print("\n[WARNING] No refresh_token received from Google.")
        print("    Fix: Go to https://myaccount.google.com/permissions")
        print("    Revoke access for this app, then run this script again.")
    else:
        print("\n[OK] Got refresh_token - login will persist permanently.")

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"\n[OK] Token saved to: {token_file.resolve()}")
    print("     StreamClipper will auto-refresh this token.")


if __name__ == "__main__":
    main()
