"""
StreamClipper — User Auth REST Routes
Endpoints for Email Registration, Login, Google OAuth, Profile, and Session Management.
"""

import logging
from typing import Optional
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, HTTPException, Response, Request, Depends, status

from server.deps import get_db
from database import Database
from server.auth_service import (
    hash_password,
    verify_password,
    create_jwt_token,
    verify_jwt_token,
    verify_google_id_token,
)

logger = logging.getLogger("streamclipper.user_auth")
router = APIRouter(prefix="/auth", tags=["User Authentication"])


# ── Pydantic Request Schemas ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    credential: str  # Google ID Token JWT


# ── Dependency: Get Current User ────────────────────────────────────────────

async def get_current_user_optional(request: Request, db: Database = Depends(get_db)) -> Optional[dict]:
    """Retrieve authenticated user from Authorization header or session cookie."""
    token = None
    # 1. Check Authorization Bearer header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    # 2. Check HTTPOnly cookie
    if not token:
        token = request.cookies.get("synclip_session")

    if not token:
        return None

    payload = verify_jwt_token(token)
    if not payload or "sub" not in payload:
        return None

    user_id = int(payload["sub"])
    user = db.get_user_by_id(user_id)
    return user


async def get_current_user(user: Optional[dict] = Depends(get_current_user_optional)) -> dict:
    """Strict dependency requiring authenticated user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/register")
async def register_user(body: RegisterRequest, response: Response, db: Database = Depends(get_db)):
    """Register a new user with email & password."""
    clean_email = body.email.strip().lower()
    if "@" not in clean_email or len(clean_email) < 5:
        raise HTTPException(status_code=400, detail="Invalid email format")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing = db.get_user_by_email(clean_email)
    if existing:
        raise HTTPException(status_code=409, detail="Account with this email already exists")

    hashed = hash_password(body.password)
    user_id = db.create_user(
        email=clean_email,
        hashed_pw=hashed,
        display_name=body.display_name or clean_email.split("@")[0],
        auth_provider="email",
    )

    token = create_jwt_token({"sub": user_id, "email": clean_email})
    response.set_cookie(
        key="synclip_session",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
        samesite="lax",
        path="/",
    )

    user = db.get_user_by_id(user_id)
    return {
        "status": "ok",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
        },
        "token": token,
    }


@router.post("/login")
async def login_user(body: LoginRequest, response: Response, db: Database = Depends(get_db)):
    """Authenticate with email & password."""
    clean_email = body.email.strip().lower()
    user = db.get_user_by_email(clean_email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(body.password, user["hashed_pw"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_jwt_token({"sub": user["id"], "email": user["email"]})
    response.set_cookie(
        key="synclip_session",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
        samesite="lax",
        path="/",
    )

    return {
        "status": "ok",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
        },
        "token": token,
    }


@router.post("/google")
async def login_google(body: GoogleAuthRequest, response: Response, db: Database = Depends(get_db)):
    """Authenticate or auto-provision user using Google OAuth ID token."""
    info = verify_google_id_token(body.credential)
    if not info or not info.get("email"):
        raise HTTPException(status_code=400, detail="Invalid or expired Google credential")

    email = info["email"].strip().lower()
    user = db.get_user_by_email(email)

    if not user:
        # Auto-provision user account
        user_id = db.create_user(
            email=email,
            hashed_pw="google_oauth_managed",
            display_name=info.get("name") or email.split("@")[0],
            avatar_url=info.get("picture") or "",
            auth_provider="google",
        )
        user = db.get_user_by_id(user_id)
    else:
        # Update avatar / name if provided
        updates = {}
        if info.get("picture") and not user.get("avatar_url"):
            updates["avatar_url"] = info["picture"]
        if info.get("name") and not user.get("display_name"):
            updates["display_name"] = info["name"]
        if updates:
            db.update_user(user["id"], **updates)
            user = db.get_user_by_id(user["id"])

    token = create_jwt_token({"sub": user["id"], "email": user["email"]})
    response.set_cookie(
        key="synclip_session",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 30,
        samesite="lax",
        path="/",
    )

    return {
        "status": "ok",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
        },
        "token": token,
    }


@router.get("/me")
async def get_current_user_profile(user: dict = Depends(get_current_user)):
    """Return current authenticated user profile."""
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"] or user["email"].split("@")[0],
            "avatar_url": user.get("avatar_url", ""),
            "auth_provider": user.get("auth_provider", "email"),
            "created_at": user.get("created_at"),
        }
    }


@router.post("/logout")
async def logout_user(response: Response):
    """Clear session cookie."""
    response.delete_cookie(key="synclip_session", path="/")
    return {"status": "ok", "message": "Logged out successfully"}
