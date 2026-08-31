"""Admin-only maintenance endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth.deps import CurrentUser, require_admin
from api.services.supporter import (
    TIER_SUPPORTER,
    TIER_SUPPORTER_PLUS,
    set_supporter_tier,
    supporter_status_payload,
    tier_label,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class SupporterGrantBody(BaseModel):
    tier: Literal["supporter", "supporter_plus"] | None = Field(
        description="Set tier, or null to revoke all supporter perks.",
    )
    expires_in: str | None = Field(
        default=None,
        description="Temporary grant duration, e.g. 1m (month), 30d, 2w, 12h, 30min.",
    )


@router.post("/supporters/{discord_id}")
def grant_supporter_tier(
    discord_id: int,
    body: SupporterGrantBody,
    _admin: CurrentUser = Depends(require_admin),
) -> dict:
    if body.tier not in (None, TIER_SUPPORTER, TIER_SUPPORTER_PLUS):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid supporter tier.")
    if body.expires_in and body.tier is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expires_in requires a tier.")
    try:
        set_supporter_tier(
            discord_id,
            body.tier,
            source="admin",
            expires_in=body.expires_in,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    payload = supporter_status_payload(discord_id)
    return {
        "discord_id": str(discord_id),
        "tier": payload.get("tier"),
        "tier_label": tier_label(payload.get("tier")),
        "active": payload.get("active"),
        "supporter_expires_at": payload.get("supporter_expires_at"),
    }
