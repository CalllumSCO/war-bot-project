"""Discord OAuth login/callback + JWT session issuing/verification (HS256)."""

from __future__ import annotations

import os
import secrets as pysecrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://localhost:3000")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
# Falls back to `{API_BASE_URL}/auth/callback` so only API_BASE_URL needs to
# be set for local/dev; override explicitly in prod if it differs.
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "").strip() or f"{API_BASE_URL}/auth/callback"

JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", str(60 * 24 * 30)))  # 30 days

DISCORD_API_BASE = "https://discord.com/api"
DISCORD_AUTHORIZE_URL = f"{DISCORD_API_BASE}/oauth2/authorize"
DISCORD_TOKEN_URL = f"{DISCORD_API_BASE}/oauth2/token"
DISCORD_USER_URL = f"{DISCORD_API_BASE}/users/@me"

STATE_TTL_SECONDS = 600

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory OAuth `state` cache (single-process CSRF guard). Fine for a small
# companion API; swap for a shared cache if the API ever runs multi-process.
_pending_states: dict[str, float] = {}


def _cleanup_states() -> None:
    now = datetime.now(timezone.utc).timestamp()
    expired = [state for state, ts in _pending_states.items() if now - ts > STATE_TTL_SECONDS]
    for state in expired:
        _pending_states.pop(state, None)


def create_access_token(data: dict[str, Any], expires_minutes: int | None = None) -> str:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured.")
    to_encode = dict(data)
    now = datetime.now(timezone.utc)
    # jose expects numeric timestamps
    to_encode["iat"] = int(now.timestamp())
    to_encode["exp"] = int((now + timedelta(minutes=expires_minutes or JWT_EXPIRES_MINUTES)).timestamp())
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured.")
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError(f"Invalid or expired token: {exc}") from exc


@router.get("/login")
def login() -> RedirectResponse:
    """Redirect the browser to Discord's OAuth consent screen."""
    if not DISCORD_CLIENT_ID or not DISCORD_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Discord OAuth is not configured.")

    _cleanup_states()
    state = pysecrets.token_urlsafe(24)
    _pending_states[state] = datetime.now(timezone.utc).timestamp()

    url = httpx.URL(
        DISCORD_AUTHORIZE_URL,
        params={
            "client_id": DISCORD_CLIENT_ID,
            "redirect_uri": DISCORD_REDIRECT_URI,
            "response_type": "code",
            "scope": "identify",
            "state": state,
        },
    )
    return RedirectResponse(str(url))


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str | None = Query(None),
) -> RedirectResponse:
    """Exchange the OAuth code for a Discord identity, then mint a JWT session."""
    _cleanup_states()
    if state is not None:
        if state not in _pending_states:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
        _pending_states.pop(state, None)

    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET or not DISCORD_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Discord OAuth is not configured.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Discord token exchange failed: {token_resp.text}",
            )
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Discord did not return an access token.")

        user_resp = await client.get(
            DISCORD_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to fetch Discord identity: {user_resp.text}",
            )
        discord_user = user_resp.json()

    discord_id = int(discord_user["id"])
    username = discord_user.get("username") or str(discord_id)
    global_name = discord_user.get("global_name")
    avatar_hash = discord_user.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
        if avatar_hash
        else None
    )

    try:
        from api.services.profile_fields import update_extended_profile_fields

        update_extended_profile_fields(
            discord_id,
            display_name=global_name or username,
            discord_username=username,
            discord_avatar_url=avatar_url,
        )
    except Exception as exc:
        print(f"⚠️ Could not cache Discord identity for {discord_id}: {exc}")

    session_token = create_access_token(
        {
            "sub": str(discord_id),
            "discord_id": discord_id,
            "username": username,
            "discriminator": discord_user.get("discriminator"),
            "global_name": global_name,
            "avatar": avatar_url,
        }
    )

    # Land on a client page that stores the JWT, then routes to /q.
    # (Redirecting to `/` used to strip ?token= via the Next.js home redirect.)
    redirect_url = httpx.URL(f"{WEB_BASE_URL.rstrip('/')}/auth/callback", params={"token": session_token})
    return RedirectResponse(str(redirect_url))


@router.post("/logout")
def logout() -> dict[str, str]:
    """Stateless JWT — client drops the token. Endpoint exists for API symmetry."""
    return {"status": "ok"}
