"""Resolve Discord rank icons from a shared icon guild (roles / emojis).

Looks up roles/emojis whose names contain Iron, Bronze, Gold, etc. on
``RANK_ICON_GUILD_ID`` (or any guild the bot is in). Falls back to local
``assets/ranks/*`` files attached to the profile message.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.config import BASE_DIR, GUILD_IDS

RANK_KEYS = (
    "unranked",
    "iron",
    "bronze",
    "silver",
    "gold",
    "platinum",
    "diamond",
    "emerald",
    "ruby",
    "paragon",
)

_ASSETS = Path(BASE_DIR) / "assets" / "ranks"
_CDN = "https://cdn.discordapp.com"

# rank -> "<:name:id>"
_emoji_mentions: Dict[str, str] = {}
# rank -> CDN URL (role icon or emoji image)
_icon_urls: Dict[str, str] = {}


def _normalize(name: str) -> Optional[str]:
    raw = (name or "").strip().lower()
    if not raw:
        return None
    cleaned = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if cleaned in RANK_KEYS:
        return cleaned
    for key in RANK_KEYS:
        if cleaned == f"rank_{key}" or cleaned.endswith(f"_{key}") or cleaned.startswith(f"{key}_"):
            return key
        if re.search(rf"\b{re.escape(key)}\b", raw):
            return key
    return None


def local_rank_path(rank: str) -> Optional[Path]:
    key = (rank or "unranked").lower()
    if key not in RANK_KEYS:
        key = "unranked"
    for name in (f"{key}.png", f"{key}.webp"):
        path = _ASSETS / name
        if path.is_file():
            return path
    return None


def emoji_mention(rank: str) -> str:
    return _emoji_mentions.get((rank or "unranked").lower(), "")


def icon_url(rank: str) -> Optional[str]:
    return _icon_urls.get((rank or "unranked").lower())


def cache_stats() -> Dict[str, int]:
    return {"emojis": len(_emoji_mentions), "urls": len(_icon_urls)}


def _candidate_guild_ids(bot: Any) -> List[int]:
    ids: List[int] = []
    raw = (os.getenv("RANK_ICON_GUILD_ID") or "").strip()
    if raw:
        try:
            ids.append(int(raw.split(",")[0].strip()))
        except ValueError:
            pass
    for gid in GUILD_IDS:
        if int(gid) not in ids:
            ids.append(int(gid))
    try:
        for guild in getattr(bot, "guilds", []) or []:
            gid = int(guild.id)
            if gid not in ids:
                ids.append(gid)
    except Exception:
        pass
    return ids


def _remember_url(key: str, url: Optional[str]) -> None:
    if key and url and key not in _icon_urls:
        _icon_urls[key] = str(url)


def _role_icon_url(role_id: Any, icon_hash: str) -> str:
    return f"{_CDN}/role-icons/{int(role_id)}/{icon_hash}.png?size=128"


def _emoji_image_url(emoji_id: Any, *, animated: bool = False) -> str:
    ext = "gif" if animated else "png"
    return f"{_CDN}/emojis/{int(emoji_id)}.{ext}?size=128"


def _ingest_role(name: str, role_id: Any, icon_hash: Optional[str], asset: Any = None) -> None:
    key = _normalize(name)
    if not key:
        return
    url = None
    if asset is not None:
        try:
            if hasattr(asset, "as_url"):
                url = asset.as_url(size=128)
            elif hasattr(asset, "url"):
                url = asset.url
        except Exception:
            url = None
    if not url and icon_hash:
        url = _role_icon_url(role_id, icon_hash)
    _remember_url(key, url)


def _ingest_emoji(name: str, emoji_id: Any, *, animated: bool = False) -> None:
    key = _normalize(name)
    if not key or not emoji_id:
        return
    prefix = "a" if animated else ""
    if key not in _emoji_mentions:
        _emoji_mentions[key] = f"<{prefix}:{name}:{int(emoji_id)}>"
    _remember_url(key, _emoji_image_url(emoji_id, animated=animated))


async def _scan_guild(bot: Any, guild_id: int) -> None:
    guild = None
    try:
        getter = getattr(bot, "get_guild", None)
        if callable(getter):
            guild = getter(guild_id)
    except Exception:
        guild = None

    # --- roles (prefer live HTTP so icon hashes are present) ---
    role_rows: List[dict] = []
    try:
        role_rows = list(await bot.http.get_roles(guild_id))
    except Exception as exc:
        print(f"⚠️ rank_icons: get_roles({guild_id}) failed: {exc}")
        if guild is not None:
            try:
                for role in getattr(guild, "roles", []) or []:
                    icon = getattr(role, "icon", None)
                    icon_hash = getattr(icon, "hash", None) if icon is not None else None
                    _ingest_role(getattr(role, "name", ""), getattr(role, "id", None), icon_hash, asset=icon)
            except Exception as exc2:
                print(f"⚠️ rank_icons: cached role scan failed: {exc2}")

    for row in role_rows:
        if not isinstance(row, dict):
            continue
        _ingest_role(str(row.get("name") or ""), row.get("id"), row.get("icon"))

    # --- custom emojis (inline <:name:id> in embed fields) ---
    try:
        emoji_rows = list(await bot.http.get_all_guild_emoji(guild_id))
    except Exception as exc:
        print(f"⚠️ rank_icons: get_all_guild_emoji({guild_id}) failed: {exc}")
        emoji_rows = []
        if guild is not None:
            try:
                for emoji in getattr(guild, "emojis", []) or []:
                    _ingest_emoji(
                        getattr(emoji, "name", "") or "",
                        getattr(emoji, "id", None),
                        animated=bool(getattr(emoji, "animated", False)),
                    )
            except Exception:
                pass

    for row in emoji_rows:
        if not isinstance(row, dict):
            continue
        _ingest_emoji(
            str(row.get("name") or ""),
            row.get("id"),
            animated=bool(row.get("animated")),
        )


async def warm_rank_icon_cache(bot: Any, *, force: bool = False) -> None:
    """Scan icon guild(s) for role icons + custom emojis."""
    if not force and _icon_urls and _emoji_mentions:
        return

    _emoji_mentions.clear()
    _icon_urls.clear()

    scanned: List[int] = []
    for guild_id in _candidate_guild_ids(bot):
        scanned.append(guild_id)
        try:
            await _scan_guild(bot, guild_id)
        except Exception as exc:
            print(f"⚠️ rank_icons: scan guild {guild_id} failed: {exc}")
        # Stop early once we have a useful set (at least a few ranks).
        if len(_icon_urls) >= 4 or len(_emoji_mentions) >= 4:
            break

    print(
        f"✅ rank_icons: {len(_emoji_mentions)} emoji(s), {len(_icon_urls)} icon URL(s) "
        f"from guild(s) {scanned or 'none'} → {sorted(_icon_urls.keys())}"
    )
