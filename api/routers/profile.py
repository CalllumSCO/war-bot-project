"""Player profile: view/edit your own cosmetics + public profile lookups."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth.deps import CurrentUser, get_current_user
from api.services.profile_fields import (
    get_extended_profile_fields,
    is_supporter,
    update_extended_profile_fields,
)
from domain.ratings import get_player_ratings_map
from utils.player_profile_store import get_profile, has_linked_fc

router = APIRouter(tags=["profile"])

_TRACKS = ("rt", "ct")
_ROLES = ("runner", "bagger")


def _ratings_summary(discord_id: int) -> dict[str, Any]:
    from utils.sr import display_sr, get_player_rating

    lanes = get_player_ratings_map(discord_id)
    # If SR table has nothing for this user, seed display lanes from legacy MMR JSON.
    if not lanes:
        try:
            from utils.player_store import DEFAULT_PLAYER_MMR, get_player
            from utils.sr import SIGMA0, mu_from_sr, rank_for_sr

            player = get_player(discord_id) or {}
            ratings = player.get("ratings") or {}
            record = player.get("record") or {}
            for track in _TRACKS:
                for role_key in _ROLES:
                    legacy = int((ratings.get(track) or {}).get(role_key, DEFAULT_PLAYER_MMR))
                    sr = int(round(legacy / 10.0)) if legacy > 2000 else int(legacy)
                    games = int(((record.get(track) or {}).get(role_key) or {}).get("wins", 0)) + int(
                        ((record.get(track) or {}).get(role_key) or {}).get("losses", 0)
                    )
                    revealed = games >= 5
                    mu = mu_from_sr(sr if sr else 1000)
                    lanes[f"{track}:{role_key}"] = {
                        "discord_id": discord_id,
                        "track": track,
                        "role": role_key,
                        "mu": float(mu),
                        "sigma": float(SIGMA0),
                        "placement_count": games,
                        "revealed": revealed,
                        "season_games": games,
                        "sr": display_sr(mu),
                        "rank": rank_for_sr(display_sr(mu), revealed=revealed),
                    }
        except Exception as exc:
            print(f"⚠️ legacy ratings fallback failed for {discord_id}: {exc}")

    summary: dict[str, Any] = {}
    for track in _TRACKS:
        track_summary: dict[str, Any] = {}
        for role_key in _ROLES:
            lane = lanes.get(f"{track}:{role_key}")
            if not lane:
                lane = get_player_rating(discord_id, track.upper(), role=role_key)
            # JSON-safe primitives only (pg may return Decimals).
            track_summary[role_key] = {
                "sr": int(lane["sr"]) if lane.get("sr") is not None else None,
                "rank": str(lane.get("rank") or "unranked"),
                "revealed": bool(lane.get("revealed")),
                "placement_count": int(lane.get("placement_count") or 0),
                "mu": float(lane["mu"]) if lane.get("mu") is not None else None,
            }
        summary[track] = track_summary
    return summary


@router.get("/me/profile")
def get_my_profile(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    base = get_profile(user.discord_id) or {}
    extended = get_extended_profile_fields(user.discord_id)
    return {
        "discord_id": user.discord_id,
        "username": extended.get("discord_username") or user.username,
        "display_name": extended.get("display_name") or user.display_name,
        "avatar": extended.get("discord_avatar_url") or user.avatar,
        "friend_code": base.get("friend_code"),
        "has_linked_fc": bool(base.get("friend_code")),
        "lounge_name": base.get("lounge_name"),
        "lounge_verified": base.get("lounge_verified", False),
        "bio": extended.get("bio"),
        "mkc_url": extended.get("mkc_url"),
        "lounge_url": extended.get("lounge_url"),
        "x_url": extended.get("x_url"),
        "bluesky_url": extended.get("bluesky_url"),
        "youtube_url": extended.get("youtube_url"),
        "twitch_url": extended.get("twitch_url"),
        "accent_color": extended.get("accent_color"),
        "supporter": extended.get("supporter", False),
        "ratings": _ratings_summary(user.discord_id),
    }


class ProfileUpdate(BaseModel):
    bio: str | None = None
    mkc_url: str | None = None
    lounge_url: str | None = None
    x_url: str | None = None
    bluesky_url: str | None = None
    youtube_url: str | None = None
    twitch_url: str | None = None
    accent_color: str | None = None


@router.patch("/me/profile")
def update_my_profile(
    body: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)

    if fields.get("accent_color") is not None and not is_supporter(user.discord_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Custom accent colors are a supporter perk.",
        )

    updated = update_extended_profile_fields(user.discord_id, **fields)
    return {"discord_id": user.discord_id, **updated}


@router.get("/users/{discord_id}")
def get_public_profile(
    discord_id: int,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    base = get_profile(discord_id)
    extended = get_extended_profile_fields(discord_id)
    if not base and not any(extended.values()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Player not found.")

    return {
        "discord_id": discord_id,
        "username": extended.get("discord_username"),
        "display_name": extended.get("display_name") or (base or {}).get("lounge_name") or str(discord_id),
        "avatar": extended.get("discord_avatar_url"),
        "bio": extended.get("bio"),
        "mkc_url": extended.get("mkc_url"),
        "lounge_url": extended.get("lounge_url"),
        "x_url": extended.get("x_url"),
        "bluesky_url": extended.get("bluesky_url"),
        "youtube_url": extended.get("youtube_url"),
        "twitch_url": extended.get("twitch_url"),
        "accent_color": extended.get("accent_color") if extended.get("supporter") else None,
        "supporter": extended.get("supporter", False),
        "friend_code": (base or {}).get("friend_code"),
        "has_linked_fc": has_linked_fc(discord_id),
        "ratings": _ratings_summary(discord_id),
    }
