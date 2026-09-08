"""
YouTube Authentication Routes — Multi-Account InstalledAppFlow with dynamic loopback port.

Features:
- Dynamically binds an available localhost port (trying 8080, then 8081, 8082, or dynamic 0)
  to completely prevent [WinError 10048] address-in-use socket crashes.
- Returns the exact Google authorization URL to the client so window.open() works reliably.
- Dedicated background worker per account handles callback with a 300-second timeout.
- Fully supports multiple independent accounts (Account 1, Account 2, Account 3, ...).
"""

import json
import logging
import re
import threading
import webbrowser
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from server.deps import get_db
import config

logger = logging.getLogger("streamclipper.auth")
router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# Thread-safe mapping of account_id -> {
#   "running": bool,
#   "error": Optional[str],
#   "auth_url": Optional[str],
#   "port": Optional[int]
# }
_auth_states: Dict[str, Dict[str, Any]] = {}
_auth_lock = threading.Lock()


class StartAuthPayload(BaseModel):
    account_id: Optional[str] = "account1"


class LogoutPayload(BaseModel):
    account_id: Optional[str] = "account1"


class AddAccountPayload(BaseModel):
    client_id: str
    client_secret: str
    name: Optional[str] = None


# ── Account Path Helpers ──────────────────────────────────────────────────────

def _get_account_paths(account_id: str = "account1") -> Dict[str, Any]:
    norm = account_id.lower().strip()
    if norm in ("account1", "primary", "default", "1"):
        return {
            "id": "account1",
            "name": "Account 1 (Primary)",
            "secrets_path": Path(config.YOUTUBE_CLIENT_SECRETS),
            "token_path": Path(config.YOUTUBE_TOKEN_FILE),
        }
    elif norm in ("account2", "2"):
        return {
            "id": "account2",
            "name": "Account 2",
            "secrets_path": Path(getattr(config, "YOUTUBE_ACCOUNT_2_CLIENT_SECRETS", "client_secrets_account2.json")),
            "token_path": Path(getattr(config, "YOUTUBE_ACCOUNT_2_TOKEN_FILE", "youtube_token_account2.json")),
        }
    elif norm in ("account3", "3"):
        return {
            "id": "account3",
            "name": "Account 3",
            "secrets_path": Path(getattr(config, "YOUTUBE_ACCOUNT_3_CLIENT_SECRETS", "client_secrets_account3.json")),
            "token_path": Path(getattr(config, "YOUTUBE_ACCOUNT_3_TOKEN_FILE", "youtube_token_account3.json")),
        }
    else:
        num_str = "".join(filter(str.isdigit, norm))
        suffix = f"_account{num_str}" if num_str else f"_{norm}"
        name = f"Account {num_str}" if num_str else f"Account {norm.title()}"
        return {
            "id": norm,
            "name": name,
            "secrets_path": config.BASE_DIR / f"client_secrets{suffix}.json",
            "token_path": config.BASE_DIR / f"youtube_token{suffix}.json",
        }


def _read_client_id(secrets_path: Path) -> Optional[str]:
    if not secrets_path.exists():
        return None
    try:
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
        installed = data.get("installed") or data.get("web") or {}
        return installed.get("client_id")
    except Exception:
        return None


def _load_creds(token_path: Path):
    """Load creds from token file. Returns None if missing/corrupt."""
    if not token_path.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        return Credentials.from_authorized_user_file(str(token_path))
    except Exception as e:
        logger.warning("Cannot load token from %s: %s", token_path, e)
        return None


def _save_creds(token_path: Path, creds):
    """Write credentials to disk."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    logger.info("YouTube token saved → %s", token_path)


def _ensure_valid(token_path: Path, creds):
    """Refresh expired token silently. Returns valid creds or None."""
    if creds is None:
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            _save_creds(token_path, creds)
            logger.info("YouTube access token refreshed automatically for %s", token_path)
            return creds
        except Exception as e:
            logger.error("Token refresh failed for %s: %s", token_path, e)
            return None
    return None


def _channel_info(creds) -> dict:
    """Fetch authenticated channel details: title, id, customUrl, etc."""
    try:
        from googleapiclient.discovery import build
        svc = build("youtube", "v3", credentials=creds)
        ch = svc.channels().list(part="snippet", mine=True).execute()
        items = ch.get("items", [])
        if items:
            snippet = items[0].get("snippet", {})
            return {
                "title": snippet.get("title", ""),
                "customUrl": snippet.get("customUrl", ""),
                "id": items[0].get("id", ""),
                "thumbnail": (snippet.get("thumbnails", {}).get("default") or {}).get("url", ""),
            }
    except Exception as e:
        logger.debug("Could not fetch channel info: %s", e)
    return {}


def _discover_all_accounts() -> List[Dict[str, Any]]:
    """Scan and list all detected YouTube accounts in workspace."""
    account_ids = ["account1", "account2", "account3"]

    for path in config.BASE_DIR.glob("client_secrets_account*.json"):
        match = re.search(r"client_secrets_account(\d+)\.json", path.name)
        if match:
            aid = f"account{match.group(1)}"
            if aid not in account_ids:
                account_ids.append(aid)

    def sort_key(aid: str) -> int:
        digits = "".join(filter(str.isdigit, aid))
        return int(digits) if digits else 999

    account_ids.sort(key=sort_key)

    results = []
    for aid in account_ids:
        paths = _get_account_paths(aid)
        secrets_path: Path = paths["secrets_path"]
        token_path: Path = paths["token_path"]
        name: str = paths["name"]

        with _auth_lock:
            state = _auth_states.get(aid, {"running": False, "error": None, "auth_url": None})

        secrets_exists = secrets_path.exists()
        token_exists = token_path.exists()
        client_id = _read_client_id(secrets_path)

        creds = _load_creds(token_path)
        creds = _ensure_valid(token_path, creds)

        connected = bool(creds and creds.refresh_token and creds.valid)
        info = _channel_info(creds) if connected else {}
        channel_title = info.get("title") if connected else None

        error = state.get("error")
        if not error and not connected:
            if not secrets_exists:
                error = f"{secrets_path.name} missing"
            elif not token_exists:
                error = "Not yet authorized"
            elif creds and not creds.refresh_token:
                error = "Token missing refresh_token — please re-authorize"

        db = get_db()
        uploads_today = db.count_uploads_today(account_id=aid)
        max_daily_uploads = getattr(config, "UPLOAD_MAX_PER_DAY", 6)
        remaining_today = max(0, max_daily_uploads - uploads_today)

        results.append({
            "id": aid,
            "name": name,
            "client_id": client_id,
            "secrets_file": str(secrets_path.name),
            "token_file": str(token_path.name),
            "secrets_exists": secrets_exists,
            "token_exists": token_exists,
            "connected": connected,
            "channel": channel_title,
            "channel_info": info,
            "pending": state.get("running", False),
            "auth_url": state.get("auth_url"),
            "error": error,
            "uploads_today": uploads_today,
            "max_daily_uploads": max_daily_uploads,
            "remaining_today": remaining_today,
        })

    return results


def _bind_oauth_redirect_server(flow):
    """
    Creates and binds a WSGI server to an open loopback port.
    Attempts port 8080 first (standard GCP redirect URI), falling back to 8081, 8082, or dynamic 0.
    """
    import wsgiref.simple_server
    from google_auth_oauthlib.flow import _RedirectWSGIApp, _WSGIRequestHandler

    msg = (
        "<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;padding:50px;background:#111;color:#fff;'>"
        "<h2 style='color:#4ade80;'>✓ YouTube Authorization Successful!</h2>"
        "<p style='color:#aaa;'>StreamClipper has acquired your upload credentials. You can close this tab now.</p>"
        "</body></html>"
    )
    wsgi_app = _RedirectWSGIApp(msg)
    wsgiref.simple_server.WSGIServer.allow_reuse_address = True

    local_server = None
    for candidate in [8080, 8081, 8082, 0]:
        try:
            local_server = wsgiref.simple_server.make_server(
                "localhost", candidate, wsgi_app, handler_class=_WSGIRequestHandler
            )
            break
        except OSError:
            continue

    if local_server is None:
        raise RuntimeError("Could not bind an open port for the local OAuth redirect server.")

    bound_port = local_server.server_port
    flow.redirect_uri = f"http://localhost:{bound_port}/"
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return local_server, wsgi_app, auth_url, bound_port


def _handle_oauth_callback(flow, local_server, wsgi_app, account_id: str, token_path: Path):
    """Background listener that waits for the Google redirect code and writes token."""
    try:
        local_server.timeout = 300  # 5-minute timeout
        local_server.handle_request()

        try:
            auth_response = wsgi_app.last_request_uri.replace("http://", "https://")
        except AttributeError:
            raise TimeoutError("Timed out waiting for response from Google OAuth authorization server.")

        flow.fetch_token(authorization_response=auth_response)
        _save_creds(token_path, flow.credentials)

        ch_name = _channel_info(flow.credentials).get("title", "Authenticated Channel")
        logger.info("OAuth completed successfully for %s! Channel: %s", account_id, ch_name)

        with _auth_lock:
            _auth_states[account_id] = {
                "running": False,
                "error": None,
                "auth_url": None,
                "port": None,
            }

    except Exception as e:
        logger.error("OAuth callback listener failed for %s: %s", account_id, e)
        with _auth_lock:
            _auth_states[account_id] = {
                "running": False,
                "error": str(e),
                "auth_url": None,
                "port": None,
            }
    finally:
        try:
            local_server.server_close()
        except Exception:
            pass


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/auth/youtube/accounts")
async def get_all_youtube_accounts():
    """Returns list of all configured YouTube accounts with live auth, quotas, and channel status."""
    accounts = _discover_all_accounts()
    connected_count = sum(1 for a in accounts if a["connected"])
    total_uploads_today = sum(a.get("uploads_today", 0) for a in accounts)
    total_max_daily = sum(a.get("max_daily_uploads", 6) for a in accounts)
    return {
        "accounts": accounts,
        "total_accounts": len(accounts),
        "connected_accounts": connected_count,
        "total_uploads_today": total_uploads_today,
        "total_max_daily": total_max_daily,
        "total_remaining_today": max(0, total_max_daily - total_uploads_today),
    }


@router.post("/auth/youtube/start")
async def start_youtube_auth(payload: Optional[StartAuthPayload] = None):
    """
    Launch the OAuth flow for the specified account.
    Returns the exact authorization URL so the frontend can immediately open it in the browser.
    """
    aid = payload.account_id if payload and payload.account_id else "account1"
    paths = _get_account_paths(aid)
    secrets_path: Path = paths["secrets_path"]
    token_path: Path = paths["token_path"]

    if not secrets_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"{secrets_path.name} not found. Please provide valid client credentials first."
        )

    with _auth_lock:
        state = _auth_states.get(aid, {})
        if state.get("running") and state.get("auth_url"):
            # Return active running flow URL
            return {
                "success": True,
                "account_id": aid,
                "auth_url": state["auth_url"],
                "port": state.get("port"),
                "message": f"Auth flow already in progress for {paths['name']}.",
            }

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        str(secrets_path),
        scopes=SCOPES,
    )

    try:
        local_server, wsgi_app, auth_url, bound_port = _bind_oauth_redirect_server(flow)
    except Exception as e:
        logger.error("Failed to bind OAuth server for %s: %s", aid, e)
        raise HTTPException(status_code=500, detail=f"Socket error: {e}")

    with _auth_lock:
        _auth_states[aid] = {
            "running": True,
            "error": None,
            "auth_url": auth_url,
            "port": bound_port,
        }

    # Start background listener
    thread = threading.Thread(
        target=_handle_oauth_callback,
        args=(flow, local_server, wsgi_app, aid, token_path),
        daemon=True,
    )
    thread.start()

    # Attempt opening system default browser directly as well
    try:
        webbrowser.open(auth_url, new=1, autoraise=True)
    except Exception:
        pass

    logger.info("OAuth server listening on port %d for %s. Auth URL issued.", bound_port, aid)

    return {
        "success": True,
        "account_id": aid,
        "auth_url": auth_url,
        "port": bound_port,
        "message": f"Please sign in with Google to authorize {paths['name']}.",
    }


@router.get("/auth/youtube/status")
async def get_youtube_auth_status(account_id: Optional[str] = Query("account1")):
    """Check connection status for a specific account (default: account1)."""
    aid = account_id or "account1"
    paths = _get_account_paths(aid)
    secrets_path: Path = paths["secrets_path"]
    token_path: Path = paths["token_path"]

    with _auth_lock:
        state = _auth_states.get(aid, {"running": False, "error": None, "auth_url": None})
    pending = state.get("running", False)
    error = state.get("error")

    creds = _load_creds(token_path)
    creds = _ensure_valid(token_path, creds)

    if creds and creds.refresh_token and creds.valid:
        info = _channel_info(creds)
        channel_title = info.get("title") or "Authenticated Channel (Upload Ready)"
        return {
            "account_id": aid,
            "connected": True,
            "channel": channel_title,
            "channel_info": info,
            "has_readonly_scope": bool(info.get("title")),
            "pending": False,
            "error": None,
        }

    if not creds or not getattr(creds, "refresh_token", None):
        reason = f"No valid token for {paths['name']} — click Connect to authorize"
        if error:
            reason = error
        elif not secrets_path.exists():
            reason = f"{secrets_path.name} missing"
        elif not token_path.exists():
            reason = "Not yet authorized"
        elif creds and not creds.refresh_token:
            reason = "Token missing refresh_token. Revoke app at myaccount.google.com/permissions and retry."

        return {
            "account_id": aid,
            "connected": False,
            "channel": None,
            "pending": pending,
            "auth_url": state.get("auth_url"),
            "error": reason,
        }

    return {
        "account_id": aid,
        "connected": False,
        "channel": None,
        "pending": pending,
        "auth_url": state.get("auth_url"),
        "error": error or "Token invalid",
    }


@router.post("/auth/youtube/logout")
@router.delete("/auth/youtube/logout")
@router.delete("/auth/youtube/token")
async def logout_youtube(payload: Optional[LogoutPayload] = None, account_id: Optional[str] = Query(None)):
    """Disconnect / Log out a YouTube account."""
    target_aid = (payload.account_id if payload and payload.account_id else account_id) or "account1"
    paths = _get_account_paths(target_aid)
    token_path: Path = paths["token_path"]

    with _auth_lock:
        _auth_states[target_aid] = {"running": False, "error": None, "auth_url": None, "port": None}

    revoked = False
    creds = _load_creds(token_path)
    if creds and getattr(creds, "token", None):
        try:
            import requests
            resp = requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": creds.token},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
            revoked = (resp.status_code == 200)
            logger.info("Revoked YouTube token on Google for %s: status %d", target_aid, resp.status_code)
        except Exception as e:
            logger.warning("Could not revoke token with Google servers: %s", e)

    if token_path.exists():
        try:
            token_path.unlink()
            logger.info("Deleted YouTube token file: %s", token_path)
        except Exception as e:
            logger.error("Failed to delete token file: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to delete token: {e}")

    return {
        "success": True,
        "account_id": target_aid,
        "connected": False,
        "revoked": revoked,
        "message": f"{paths['name']} disconnected successfully.",
    }


@router.post("/auth/youtube/add")
async def add_youtube_account(payload: AddAccountPayload):
    """Register a new account credentials file and append to .env."""
    if not payload.client_id or not payload.client_secret:
        raise HTTPException(status_code=400, detail="Both client_id and client_secret are required.")

    accounts = _discover_all_accounts()
    max_idx = 1
    for a in accounts:
        match = re.search(r"account(\d+)", a["id"])
        if match:
            max_idx = max(max_idx, int(match.group(1)))
    new_idx = max_idx + 1
    new_aid = f"account{new_idx}"

    secrets_filename = f"client_secrets_account{new_idx}.json"
    token_filename = f"youtube_token_account{new_idx}.json"
    secrets_path = config.BASE_DIR / secrets_filename

    secrets_data = {
        "installed": {
            "client_id": payload.client_id.strip(),
            "project_id": f"streamclipper-account{new_idx}",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": payload.client_secret.strip(),
            "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
        }
    }
    secrets_path.write_text(json.dumps(secrets_data, indent=2), encoding="utf-8")
    logger.info("Created secrets file: %s", secrets_path)

    env_path = config.BASE_DIR / ".env"
    if env_path.exists():
        try:
            env_content = env_path.read_text(encoding="utf-8")
            account_block = (
                f"\n# ── YouTube Data API v3 (Account {new_idx}) ─────────────────────\n"
                f"YOUTUBE_ACCOUNT_{new_idx}_CLIENT_ID={payload.client_id.strip()}\n"
                f"YOUTUBE_ACCOUNT_{new_idx}_CLIENT_SECRET={payload.client_secret.strip()}\n"
                f"YOUTUBE_ACCOUNT_{new_idx}_CLIENT_SECRETS={secrets_filename}\n"
                f"YOUTUBE_ACCOUNT_{new_idx}_TOKEN_FILE={token_filename}\n"
            )
            env_path.write_text(env_content + account_block, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to update .env: %s", e)

    return {
        "success": True,
        "account_id": new_aid,
        "message": f"Account {new_idx} added successfully. Ready to authorize.",
        "secrets_file": secrets_filename,
        "token_file": token_filename,
    }
