"""
YouTube Authentication Routes — Proper InstalledAppFlow with auto-refresh.

Strategy:
- Uses InstalledAppFlow.run_local_server() — the ONLY Google-approved method for
  installed/desktop apps that reliably returns a refresh_token and avoids bot-blocking.
- A background thread runs the flow so the API doesn't block.
- Frontend polls /status until connected=True.
- On subsequent starts, the token is auto-refreshed silently — no login ever needed again.
"""

import logging
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException

import config

logger = logging.getLogger("streamclipper.auth")
router = APIRouter()

SCOPES     = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = Path(config.YOUTUBE_TOKEN_FILE)
SECRETS_PATH = Path(config.YOUTUBE_CLIENT_SECRETS)

# Shared auth-flow state (thread-safe enough for single-user dashboard)
_auth_state: dict = {"running": False, "error": None}


# ── Credential Helpers ────────────────────────────────────────────────────────

def _load_creds():
    """Load creds from token file. Returns None if missing/corrupt."""
    if not TOKEN_PATH.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        return Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except Exception as e:
        logger.warning("Cannot load token: %s", e)
        return None


def _save_creds(creds):
    """Write credentials (including refresh_token) to disk."""
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    logger.info("YouTube token saved → %s", TOKEN_PATH)


def _ensure_valid(creds):
    """
    Refresh expired token silently.
    Returns valid creds, or None if refresh fails.
    """
    if creds is None:
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            _save_creds(creds)
            logger.info("YouTube access token refreshed automatically")
            return creds
        except Exception as e:
            logger.error("Token refresh failed: %s", e)
            return None
    return None


def _channel_name(creds) -> str | None:
    """Fetch the authenticated channel's display name."""
    try:
        from googleapiclient.discovery import build
        svc = build("youtube", "v3", credentials=creds)
        ch = svc.channels().list(part="snippet", mine=True).execute()
        items = ch.get("items", [])
        if items:
            return items[0]["snippet"]["title"]
    except Exception:
        pass
    return None


def _run_auth_flow():
    """
    Background thread: opens the system browser, handles OAuth callback on a
    random localhost port, saves token. This is Google's recommended approach
    for installed/desktop apps and always returns a refresh_token.
    """
    global _auth_state
    _auth_state = {"running": True, "error": None}

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(
            str(SECRETS_PATH),
            scopes=SCOPES,
        )

        # run_local_server:
        # - Picks a random free port automatically (port=0)
        # - Opens the system default browser to the Google sign-in page
        # - Waits for the OAuth redirect callback
        # - Closes the local server when done
        # access_type=offline + prompt=consent → ALWAYS get a refresh_token
        creds = flow.run_local_server(
            port=8080,
            access_type="offline",
            prompt="consent",          # Force consent screen so refresh_token is issued
            open_browser=True,
        )

        if not creds.refresh_token:
            # This can happen if the user has previously revoked and re-authorized
            # without revoking. Solution: revoke on Google, then retry.
            logger.warning(
                "No refresh_token in response. "
                "User should revoke at https://myaccount.google.com/permissions and retry."
            )

        _save_creds(creds)
        logger.info("YouTube auth complete. Channel: %s", _channel_name(creds) or "unknown")
        _auth_state["running"] = False

    except Exception as e:
        logger.error("Auth flow failed: %s", e)
        _auth_state["error"] = str(e)
        _auth_state["running"] = False


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/auth/youtube/start")
async def start_youtube_auth():
    """
    Launch the OAuth flow in a background thread.
    This opens the system browser automatically — user just signs in.
    Frontend should poll /auth/youtube/status until connected=True.
    """
    if not SECRETS_PATH.exists():
        raise HTTPException(
            status_code=400,
            detail="client_secrets.json not found in the backend directory."
        )

    if _auth_state.get("running"):
        return {"message": "Auth flow already in progress — check the browser window"}

    # If already connected with a valid token, don't re-auth
    creds = _ensure_valid(_load_creds())
    if creds and creds.refresh_token:
        return {"message": "Already connected"}

    thread = threading.Thread(target=_run_auth_flow, daemon=True)
    thread.start()
    return {"message": "Browser opened — please sign in with your Google account"}


@router.get("/auth/youtube/status")
async def get_youtube_auth_status():
    """
    Check connection status. Auto-refreshes expired tokens.
    Returns:
      connected: True/False
      channel: display name if connected
      pending: True if auth flow is currently running
      error: error message if flow failed
    """
    pending = _auth_state.get("running", False)
    error   = _auth_state.get("error")

    creds = _load_creds()
    creds = _ensure_valid(creds)

    if creds and creds.refresh_token and creds.valid:
        return {
            "connected": True,
            "channel": _channel_name(creds),
            "pending": False,
            "error": None,
        }

    if not creds or not getattr(creds, "refresh_token", None):
        reason = "No valid token — click Connect YouTube to authorize"
        if error:
            reason = error
        elif not TOKEN_PATH.exists():
            reason = "Not yet authorized"
        elif creds and not creds.refresh_token:
            reason = (
                "Token missing refresh_token. "
                "Revoke app access at myaccount.google.com/permissions, then reconnect."
            )
        return {"connected": False, "pending": pending, "error": reason}

    return {"connected": False, "pending": pending, "error": error or "Token invalid"}


@router.delete("/auth/youtube/token")
async def delete_youtube_token():
    """
    Delete the saved token so the user can re-authorize from scratch.
    Use this if the token has no refresh_token and auto-refresh is broken.
    """
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        logger.info("YouTube token deleted by user request")
        return {"message": "Token deleted — you can now reconnect"}
    return {"message": "No token file found"}

