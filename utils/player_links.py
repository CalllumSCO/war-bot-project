"""Resolve Discord users to Wii friend codes via Lounge API + local profiles."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from utils.lounge_api import (
    LoungeAPIError,
    fetch_host_friend_codes,
    lookup_lounge_player_by_discord,
    lookup_players_by_discord_ids,
)
from utils.player_profile_store import get_profile, has_linked_fc, upsert_profile
from utils.wiimmfi import friend_code_key, normalize_friend_code

LOUNGE_PROFILE_URL = (
    "https://mkwlounge.gg/ladder/player.php?player_id={player_id}&ladder_id=19"
)
MKC_PROFILE_URL = "https://mkcentral.com/en-us/registry/players/profile?id={player_id}"


def lounge_profile_url(lounge_player_id: Any) -> Optional[str]:
    try:
        pid = int(lounge_player_id)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    return LOUNGE_PROFILE_URL.format(player_id=pid)


def mkc_profile_url(mkc_player_id: Any) -> Optional[str]:
    try:
        pid = int(mkc_player_id)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    return MKC_PROFILE_URL.format(player_id=pid)


def _as_discord_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _mkc_linked_discord_id(player: Dict[str, Any]) -> Optional[int]:
    """Discord id registered on an MKC player row, if any."""
    discord = player.get("discord")
    if isinstance(discord, dict):
        found = _as_discord_id(discord.get("discord_id") or discord.get("id"))
        if found is not None:
            return found
    return _as_discord_id(
        player.get("discord_id")
        or player.get("discord_user_id")
        or player.get("discordId")
    )


async def preload_external_profile_links(
    discord_id: int,
    *,
    friend_code: Optional[str] = None,
    lounge_player_id: Any = None,
) -> None:
    """
    Best-effort: fill empty lounge_url / mkc_url when ownership matches.

    Anti-alt: only attach Lounge/MKC profile URLs when the Discord account on
    that external profile matches `discord_id`. Never overwrites existing URLs.
    Never raises — failures are silent so FC linking always continues.

    `lounge_player_id` is accepted for call-site compatibility but ignored;
    Lounge URLs are only set via Discord-owned Lounge lookup.
    """
    _ = lounge_player_id
    try:
        await _preload_external_profile_links_inner(discord_id, friend_code=friend_code)
    except Exception as exc:
        print(f"⚠️ preload_external_profile_links failed for {discord_id}: {exc}")


async def _preload_external_profile_links_inner(
    discord_id: int,
    *,
    friend_code: Optional[str] = None,
) -> None:
    try:
        from api.services.profile_fields import (
            get_extended_profile_fields,
            update_extended_profile_fields,
        )
    except Exception:
        return

    try:
        extended = get_extended_profile_fields(discord_id)
    except Exception:
        return

    updates: Dict[str, Any] = {}

    need_lounge = not (extended.get("lounge_url") or "").strip()
    if need_lounge:
        lounge_player = None
        try:
            lounge_player = await lookup_lounge_player_by_discord(discord_id)
        except Exception:
            lounge_player = None
        if lounge_player:
            # player.php was queried by discord_id → ownership already matches
            url = lounge_profile_url(lounge_player.get("player_id"))
            if url:
                updates["lounge_url"] = url

    need_mkc = not (extended.get("mkc_url") or "").strip()
    fc = normalize_friend_code(friend_code or "")
    if need_mkc and fc:
        try:
            from utils.mkcentral import lookup_mkc_player_by_fc

            mkc_player = await lookup_mkc_player_by_fc(fc)
        except Exception:
            mkc_player = None
        if mkc_player and _mkc_linked_discord_id(mkc_player) == int(discord_id):
            mkc_id = mkc_player.get("id") or mkc_player.get("player_id")
            url = mkc_profile_url(mkc_id)
            if url:
                updates["mkc_url"] = url

    if not updates:
        return
    update_extended_profile_fields(discord_id, **updates)


def _fc_from_row(row: Dict[str, Any]) -> Optional[str]:
    for key in ("fc", "friend_code", "friendcode", "wiimmfi_fc"):
        fc = normalize_friend_code(str(row.get(key, "")))
        if fc:
            return fc
    return None


async def verify_cached_fcs_against_wiimmfi(
    discord_ids: List[int],
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Compare cached profile FCs to live WiimmFI/Lounge FCs (when available).

    Returns (mismatches, verified_ids).
    - mismatches: players whose live FC differs from the cached link
    - verified_ids: players whose live FC matched cache (eligible for upgrade)
    Non-Lounge / offline players with no live FC are skipped (not an error).
    """
    unique_ids = sorted({int(d) for d in discord_ids if d})
    if not unique_ids:
        return [], []

    try:
        rows = await lookup_players_by_discord_ids(unique_ids, lounge_verified_only=False)
    except LoungeAPIError:
        return [], []

    live_by_discord: Dict[int, str] = {}
    for row in rows:
        raw_id = row.get("discord_user_id") or row.get("discord_id")
        if raw_id is None:
            continue
        try:
            discord_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        fc = _fc_from_row(row)
        if fc:
            live_by_discord[discord_id] = fc

    mismatches: List[Dict[str, Any]] = []
    verified_ids: List[int] = []
    for discord_id in unique_ids:
        live_fc = live_by_discord.get(discord_id)
        if not live_fc:
            continue
        profile = get_profile(discord_id)
        cached = normalize_friend_code((profile or {}).get("friend_code", ""))
        if not cached:
            continue
        if friend_code_key(cached) != friend_code_key(live_fc):
            mismatches.append(
                {
                    "discord_id": discord_id,
                    "player": (profile or {}).get("lounge_name") or str(discord_id),
                    "cached_fc": cached,
                    "live_fc": live_fc,
                }
            )
            continue

        verified_ids.append(discord_id)
        fields: Dict[str, Any] = {
            "lounge_verified": True,
            "last_fc_verified_at": datetime.utcnow().isoformat(),
        }
        if (profile or {}).get("link_source") in ("manual", "lounge+manual", "hostfc"):
            fields["link_source"] = "lounge"
        upsert_profile(discord_id, **fields)

    return mismatches, verified_ids


def _is_lounge_missing_player(exc: BaseException) -> bool:
    """True when Lounge simply has no account for this Discord user (not a config failure)."""
    msg = str(exc).lower()
    return any(
        needle in msg
        for needle in (
            "invalid discord user id",
            "player not found",
            "no player found",
            "no results",
            "unknown player",
        )
    )


async def try_lounge_link(discord_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    """
    Attempt automatic Lounge link by Discord ID.

    Returns (profile, lounge_player, error_message).
    - profile: fully linked when an FC was available from wiimmfi.php
    - lounge_player: player.php identity when Lounge account exists but FC still needed
    - error_message: soft advisory only — callers should still offer manual FC entry
      (no Lounge account / API hiccup must not block linking)
    """
    lounge_player: Optional[Dict[str, Any]] = None
    wiimmfi_row: Optional[Dict[str, Any]] = None
    fc: Optional[str] = None
    soft_error: Optional[str] = None

    player_result, wiimmfi_result = await asyncio.gather(
        lookup_lounge_player_by_discord(discord_id),
        lookup_players_by_discord_ids([discord_id], lounge_verified_only=False),
        return_exceptions=True,
    )

    if isinstance(player_result, Exception):
        if _is_lounge_missing_player(player_result):
            lounge_player = None
        else:
            # Config/network issues: still allow manual FC; keep a soft note.
            soft_error = str(player_result)
            lounge_player = None
    else:
        lounge_player = player_result

    if isinstance(wiimmfi_result, Exception):
        pass
    elif wiimmfi_result:
        wiimmfi_row = wiimmfi_result[0]
        fc = _fc_from_row(wiimmfi_row)

    if not fc and not lounge_player:
        return None, None, soft_error

    lounge_name = None
    lounge_player_id = None
    if lounge_player:
        lounge_name = lounge_player.get("player_name") or lounge_player.get("name")
        lounge_player_id = lounge_player.get("player_id")
    elif wiimmfi_row:
        lounge_name = wiimmfi_row.get("name") or wiimmfi_row.get("player_name")
        lounge_player_id = wiimmfi_row.get("player_id")

    if fc:
        profile = upsert_profile(
            discord_id,
            friend_code=fc,
            lounge_name=lounge_name,
            lounge_player_id=lounge_player_id,
            link_source="lounge",
            lounge_verified=bool(
                (wiimmfi_row or {}).get("lounge_verified")
                or (wiimmfi_row or {}).get("verified")
                or lounge_player
            ),
        )
        try:
            await preload_external_profile_links(
                discord_id,
                friend_code=fc,
                lounge_player_id=lounge_player_id,
            )
        except Exception:
            pass
        return profile, lounge_player, None

    return None, lounge_player, soft_error


async def link_manual_friend_code(
    discord_id: int,
    raw_fc: str,
    *,
    lounge_player: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    fc = normalize_friend_code(raw_fc)
    if not fc:
        return None, "Invalid friend code. Use `XXXX-XXXX-XXXX`."

    fields: Dict[str, Any] = {
        "friend_code": fc,
        "link_source": "lounge+manual" if lounge_player else "manual",
        "lounge_verified": bool(lounge_player),
    }
    lounge_player_id = None
    if lounge_player:
        fields["lounge_name"] = lounge_player.get("player_name") or lounge_player.get("name")
        lounge_player_id = lounge_player.get("player_id")
        fields["lounge_player_id"] = lounge_player_id

    profile = upsert_profile(discord_id, **fields)
    try:
        await preload_external_profile_links(
            discord_id,
            friend_code=fc,
            lounge_player_id=lounge_player_id or (profile or {}).get("lounge_player_id"),
        )
    except Exception:
        pass
    return profile, None


async def resolve_friend_code(
    discord_id: int,
    *,
    guild_id: Optional[int] = None,
) -> Optional[str]:
    profile = get_profile(discord_id)
    if profile and profile.get("friend_code"):
        return profile["friend_code"]

    try:
        rows = await lookup_players_by_discord_ids([discord_id], lounge_verified_only=False)
        if rows:
            fc = _fc_from_row(rows[0])
            if fc:
                lounge_player = None
                try:
                    lounge_player = await lookup_lounge_player_by_discord(discord_id)
                except LoungeAPIError:
                    pass
                lounge_player_id = (lounge_player or rows[0]).get("player_id")
                upsert_profile(
                    discord_id,
                    friend_code=fc,
                    lounge_name=(lounge_player or rows[0]).get("player_name")
                    or rows[0].get("name"),
                    lounge_player_id=lounge_player_id,
                    link_source="lounge",
                    lounge_verified=True,
                )
                await preload_external_profile_links(
                    discord_id,
                    friend_code=fc,
                    lounge_player_id=lounge_player_id,
                )
                return fc
    except LoungeAPIError:
        pass

    if guild_id:
        try:
            host_rows = await fetch_host_friend_codes(guild_id, [discord_id])
            if host_rows:
                fc = normalize_friend_code(host_rows[0].get("fc", ""))
                if fc:
                    upsert_profile(discord_id, friend_code=fc, link_source="hostfc")
                    await preload_external_profile_links(discord_id, friend_code=fc)
                    return fc
        except LoungeAPIError:
            pass

    return None


async def lineup_missing_links(
    lineup: List[Dict[str, Any]],
    *,
    guild_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    missing = []
    for player in lineup or []:
        discord_id = player.get("discord_id")
        if not discord_id:
            continue
        fc = await resolve_friend_code(int(discord_id), guild_id=guild_id)
        if not fc:
            missing.append(player)
    return missing


async def require_linked_fc(ctx, guild_id: int | None = None) -> bool:
    """Return True if the user has a resolvable friend code."""
    if has_linked_fc(ctx.author.id):
        return True
    fc = await resolve_friend_code(ctx.author.id, guild_id=guild_id)
    if fc:
        return True

    message = (
        "You need a linked Wii friend code before joining a queue.\n"
        "Run **`/profile link`** — if you have Lounge linked to Discord it can auto-fill, "
        "otherwise enter your WiimmFI FC in the modal.\n"
        "Then tap **Join as Runner/Bagger** again."
    )
    try:
        await ctx.send(message, ephemeral=True)
    except Exception:
        # After defer(), some builds prefer a plain followup.
        try:
            await ctx.send(message)
        except Exception as exc:
            print(f"⚠️ require_linked_fc notify failed: {exc}")
    return False
