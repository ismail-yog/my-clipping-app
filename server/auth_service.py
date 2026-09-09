"""
StreamClipper — User Authentication & JWT Service
Provides secure password hashing (PBKDF2-HMAC-SHA256), cryptographic salt,
JWT session token issuance, and Google ID token validation.
"""

import os
import time
import hmac
import json
import base64
import hashlib
import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import config
from database import Database

logger = logging.getLogger("streamclipper.auth_service")

# Secret key for JWT HMAC signing
JWT_SECRET = getattr(config, "SECRET_KEY", "streamclipper-production-secret-key-salt-98214")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 60 * 60 * 24 * 30  # 30 days persistent session


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with cryptographically strong salt."""
    salt = os.urandom(16)
    kdf = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${kdf.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time verification of password against stored PBKDF2 hash."""
    try:
        salt_hex, key_hex = hashed_password.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        candidate_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(candidate_key, expected_key)
    except Exception:
        return False


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(data_str: str) -> bytes:
    rem = len(data_str) % 4
    if rem > 0:
        data_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data_str)


def create_jwt_token(payload: Dict[str, Any], expires_in: int = JWT_EXPIRATION_SECONDS) -> str:
    """Issue signed HMAC-SHA256 JWT token with expiration timestamp."""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    body = dict(payload)
    now = int(time.time())
    body["iat"] = now
    body["exp"] = now + expires_in

    header_b64 = _b64_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        JWT_SECRET.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256
    ).digest()
    sig_b64 = _b64_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate signature and expiration of JWT token."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        expected_sig = hmac.new(
            JWT_SECRET.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("utf-8"),
            hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64_encode(expected_sig), sig_b64):
            return None
        payload = json.loads(_b64_decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception as e:
        logger.debug("JWT verification error: %s", e)
        return None


def verify_google_id_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify Google OAuth 2.0 ID Token payload.
    Supports google-auth library if available, falling back to Google tokeninfo endpoint.
    """
    if not id_token or not id_token.strip():
        return None
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        # Note: client_id is optional for basic verification; verify token payload structure
        id_info = google_id_token.verify_oauth2_token(id_token, google_requests.Request())
        return {
            "email": id_info.get("email"),
            "name": id_info.get("name") or id_info.get("given_name") or "",
            "picture": id_info.get("picture") or "",
            "sub": id_info.get("sub"),
        }
    except Exception:
        pass

    # HTTP Fallback to Google TokenInfo verification endpoint
    try:
        import requests
        resp = requests.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token.strip()}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "email": data.get("email"),
                "name": data.get("name") or "",
                "picture": data.get("picture") or "",
                "sub": data.get("sub"),
            }
    except Exception as e:
        logger.warning("Google tokeninfo fallback failed: %s", e)

    return None
