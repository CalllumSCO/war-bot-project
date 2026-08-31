"""Supporter status and perk info for the logged-in user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth.deps import CurrentUser, get_current_user
from api.services.profile_fields import update_extended_profile_fields
from api.services.supporter import has_supporter_tier, supporter_status_payload

router = APIRouter(tags=["supporter"])


@router.get("/me/supporter")
def get_my_supporter_status(user: CurrentUser = Depends(get_current_user)) -> dict:
    return supporter_status_payload(user.discord_id)


class SupporterCosmeticsUpdate(BaseModel):
    accent_color: str | None = None
    lineup_name_color: str | None = None
    favorite_track: str | None = None


@router.patch("/me/supporter")
def update_supporter_cosmetics(
    body: SupporterCosmeticsUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    if not has_supporter_tier(user.discord_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Supporter cosmetics require an active membership.",
        )
    fields = body.model_dump(exclude_unset=True)
    if fields:
        update_extended_profile_fields(user.discord_id, **fields)
    return supporter_status_payload(user.discord_id)
