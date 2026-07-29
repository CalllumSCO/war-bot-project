"""FastAPI dependencies: current-user extraction from a Bearer JWT + FC gate."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from api.auth.discord import decode_access_token


class CurrentUser(BaseModel):
    discord_id: int
    username: str
    discriminator: str | None = None
    global_name: str | None = None
    avatar: str | None = None

    @property
    def display_name(self) -> str:
        return self.global_name or self.username or str(self.discord_id)


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    # EventSource (SSE) cannot set custom headers, so also accept the token
    # as a query param for the /events stream.
    return request.query_params.get("token") or request.query_params.get("access_token")


def get_current_user(request: Request) -> CurrentUser:
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        ) from exc

    raw_id = payload.get("sub") or payload.get("discord_id")
    if not raw_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed session token.",
        )

    return CurrentUser(
        discord_id=int(raw_id),
        username=payload.get("username") or str(raw_id),
        discriminator=payload.get("discriminator"),
        global_name=payload.get("global_name"),
        avatar=payload.get("avatar"),
    )


def require_linked_fc(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Gate for queue actions: the user must have a linked Wii friend code."""
    from utils.player_profile_store import has_linked_fc

    try:
        linked = has_linked_fc(user.discord_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not verify friend code link: {exc}",
        ) from exc

    if not linked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Link your Wii friend code first (Discord `/profile link`).",
        )
    return user
