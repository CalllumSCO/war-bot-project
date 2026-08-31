"""Player profile: view/edit your own cosmetics + public profile lookups."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth.deps import CurrentUser, get_current_user
from api.services.profile_fields import (
    get_extended_profile_fields,
    is_supporter,
    update_extended_profile_fields,
)
from utils.favorite_lane import normalize_favorite_lane
from api.services.profile_lookup import resolve_profile_identifier
from api.services.supporter import (
    has_supporter_tier,
    is_supporter_plus,
    normalize_alias,
    tier_label,
    validate_alias,
)
from domain.ratings import get_player_ratings_map
from utils.db import get_conn, use_json_stores
from utils.player_profile_store import get_profile, has_linked_fc

router = APIRouter(tags=["profile"])

_TRACKS = ("rt", "ct")
_ROLES = ("runner", "bagger")


def _ratings_summary(discord_id: int) -> dict[str, Any]:
    from utils.sr import display_sr, get_player_rating

    lanes = get_player_ratings_map(discord_id)
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
            track_summary[role_key] = {
                "sr": int(lane["sr"]) if lane.get("sr") is not None else None,
                "rank": str(lane.get("rank") or "unranked"),
                "revealed": bool(lane.get("revealed")),
                "placement_count": int(lane.get("placement_count") or 0),
                "mu": float(lane["mu"]) if lane.get("mu") is not None else None,
            }
        summary[track] = track_summary
    return summary


def _profile_payload(discord_id: int, user: CurrentUser | None = None) -> dict[str, Any]:
    base = get_profile(discord_id) or {}
    extended = get_extended_profile_fields(discord_id)
    tier = extended.get("supporter_tier")
    active = bool(tier or extended.get("supporter"))
    return {
        "discord_id": str(discord_id),
        "username": extended.get("discord_username") or (user.username if user else None),
        "display_name": extended.get("display_name")
        or (user.display_name if user else None)
        or (base or {}).get("lounge_name")
        or str(discord_id),
        "avatar": extended.get("discord_avatar_url") or (user.avatar if user else None),
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
        "accent_color": extended.get("accent_color") if active else None,
        "lineup_name_color": extended.get("lineup_name_color") if active else None,
        "favorite_track": extended.get("favorite_track") if active else None,
        "profile_alias": extended.get("profile_alias") if tier == "supporter_plus" else None,
        "profile_path": (
            f"/u/{extended.get('profile_alias')}"
            if tier == "supporter_plus" and extended.get("profile_alias")
            else f"/u/{discord_id}"
        ),
        "supporter": active,
        "supporter_tier": tier,
        "supporter_tier_label": tier_label(tier if active else None),
        "display_name_custom": bool(extended.get("display_name_custom")),
        "ratings": _ratings_summary(discord_id),
    }


def _alias_taken(alias: str, discord_id: int) -> bool:
    if use_json_stores():
        from utils.player_profile_store import _load_all

        for key in (_load_all().get("profiles") or {}).keys():
            try:
                did = int(key)
            except (TypeError, ValueError):
                continue
            if did == discord_id:
                continue
            extended = get_extended_profile_fields(did)
            if (extended.get("profile_alias") or "").strip().lower() == alias:
                return True
        return False

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT 1 FROM players
                    WHERE LOWER(profile_alias) = %s AND discord_id <> %s
                    LIMIT 1
                    """,
                    (alias, int(discord_id)),
                )
                return cursor.fetchone() is not None
            finally:
                cursor.close()
    except Exception:
        return False


@router.get("/me/profile")
async def get_my_profile(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    base = get_profile(user.discord_id) or {}
    if base.get("friend_code") and (
        not (get_extended_profile_fields(user.discord_id).get("mkc_url") or "").strip()
        or not (get_extended_profile_fields(user.discord_id).get("lounge_url") or "").strip()
    ):
        from utils.player_links import preload_external_profile_links

        try:
            await preload_external_profile_links(
                user.discord_id,
                friend_code=base.get("friend_code"),
                lounge_player_id=base.get("lounge_player_id"),
            )
        except Exception:
            pass
    payload = _profile_payload(user.discord_id, user)
    try:
        from utils.lineup_sr import lineup_cards_for_profile

        payload["lineup_ratings"] = lineup_cards_for_profile(user.discord_id)
    except Exception:
        payload["lineup_ratings"] = []
    return payload


class ProfileUpdate(BaseModel):
    bio: str | None = None
    mkc_url: str | None = None
    lounge_url: str | None = None
    x_url: str | None = None
    bluesky_url: str | None = None
    youtube_url: str | None = None
    twitch_url: str | None = None
    accent_color: str | None = None
    lineup_name_color: str | None = None
    display_name: str | None = Field(default=None, max_length=64)
    favorite_track: str | None = None
    profile_alias: str | None = Field(default=None, max_length=32)


class FriendCodeLinkBody(BaseModel):
    friend_code: str | None = None


@router.patch("/me/profile")
def update_my_profile(
    body: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)

    if fields.get("accent_color") is not None and not is_supporter(user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Custom accent colors are a supporter perk.")
    if fields.get("lineup_name_color") is not None and not is_supporter(user.discord_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Custom match/chat name colors are a supporter perk.",
        )
    if fields.get("display_name") is not None and not has_supporter_tier(user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Custom display names are a supporter perk.")
    if fields.get("favorite_track") is not None and not has_supporter_tier(user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Favorite track pinning is a supporter perk.")
    if "profile_alias" in fields and not is_supporter_plus(user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vanity profile URLs are a Supporter+ perk.")

    updates: dict[str, Any] = dict(fields)
    if "display_name" in updates:
        name = (updates.pop("display_name") or "").strip()
        if not name:
            updates["display_name"] = None
            updates["display_name_custom"] = False
        else:
            updates["display_name"] = name[:64]
            updates["display_name_custom"] = True

    if "profile_alias" in updates:
        raw_alias = updates.pop("profile_alias")
        if raw_alias is None or not str(raw_alias).strip():
            updates["profile_alias"] = None
        else:
            alias = normalize_alias(str(raw_alias))
            error = validate_alias(alias)
            if error:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
            if _alias_taken(alias, user.discord_id):
                raise HTTPException(status.HTTP_409_CONFLICT, "That alias is already taken.")
            updates["profile_alias"] = alias

    if "favorite_track" in updates:
        if updates["favorite_track"] is None:
            pass
        else:
            try:
                updates["favorite_track"] = normalize_favorite_lane(str(updates["favorite_track"]))
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if updates:
        update_extended_profile_fields(user.discord_id, **updates)
    return _profile_payload(user.discord_id, user)


@router.post("/me/friend-code")
async def link_my_friend_code(
    body: FriendCodeLinkBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    from utils.lounge_api import LoungeAPIError, lookup_lounge_player_by_discord
    from utils.player_links import link_manual_friend_code, try_lounge_link

    raw = (body.friend_code or "").strip()
    if not raw:
        profile = None
        lounge_player = None
        try:
            profile, lounge_player, _soft_error = await try_lounge_link(user.discord_id)
        except Exception:
            profile, lounge_player = None, None
        if profile and profile.get("friend_code"):
            return await get_my_profile(user)

        current = await get_my_profile(user)
        if lounge_player:
            hint = (
                "Lounge found your Discord account but has no FC — "
                "enter your WiimmFI friend code below."
            )
        else:
            hint = "Enter your WiimmFI friend code (XXXX-XXXX-XXXX) below."
        return {**current, "auto_link": False, "auto_link_hint": hint}

    lounge_player = None
    try:
        lounge_player = await lookup_lounge_player_by_discord(user.discord_id)
    except LoungeAPIError:
        lounge_player = None
    except Exception:
        lounge_player = None

    linked, error = await link_manual_friend_code(
        user.discord_id,
        raw,
        lounge_player=lounge_player,
    )
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    if not linked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not save friend code.")
    return await get_my_profile(user)


@router.get("/users/{identifier}")
def get_public_profile(identifier: str) -> dict[str, Any]:
    """Public profile by Discord snowflake or Supporter+ alias."""
    discord_id = resolve_profile_identifier(identifier)
    if discord_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Player not found.")

    base = get_profile(discord_id)
    extended = get_extended_profile_fields(discord_id)

    has_base = bool(
        base
        and (
            base.get("friend_code")
            or base.get("lounge_name")
            or base.get("lounge_player_id")
        )
    )
    skip_keys = {"supporter", "supporter_tier", "display_name_custom", "lineup_name_color", "profile_alias"}
    has_extended = any(
        value not in (None, "", False)
        for key, value in extended.items()
        if key not in skip_keys
    )
    if not has_base and not has_extended and not extended.get("supporter_tier"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Player not found.")

    return _profile_payload(discord_id)
