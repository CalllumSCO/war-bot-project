"""Supporter tiers, perk catalog, Patreon sync, and patron listings."""

from __future__ import annotations

import calendar
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from api.services.profile_fields import get_extended_profile_fields, update_extended_profile_fields
from utils.db import get_conn, use_json_stores

SupporterTier = Literal["supporter", "supporter_plus"]
TierOrNone = SupporterTier | None

TIER_SUPPORTER: SupporterTier = "supporter"
TIER_SUPPORTER_PLUS: SupporterTier = "supporter_plus"
ACTIVE_PATRON_STATUSES = frozenset({"active_patron"})

TIER_RANK = {TIER_SUPPORTER: 1, TIER_SUPPORTER_PLUS: 2}

ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")
RESERVED_ALIASES = frozenset(
    {
        "admin",
        "api",
        "auth",
        "edit",
        "guide",
        "info",
        "login",
        "match",
        "me",
        "q",
        "queue",
        "supporter",
        "supporters",
        "users",
        "wars",
        "webhooks",
    }
)

PERK_STATUS_WIP = "wip"
PERK_STATUS_LIVE = "live"
PERK_STATUS_SOON = "soon"

PUBLIC_PERK_CATALOG: tuple[dict[str, Any], ...] = (
    # --- Supporter (live) ---
    {
        "id": "queue_preview",
        "tier": TIER_SUPPORTER,
        "title": "Queue peeking",
        "description": "Preview the Available board (ranks only) before you join queue.",
        "status": PERK_STATUS_LIVE,
    },
    {
        "id": "display_name",
        "tier": TIER_SUPPORTER,
        "title": "Custom display name",
        "description": "Set the name shown on your profile and in match lineups.",
        "status": PERK_STATUS_LIVE,
    },
    {
        "id": "favorite_track",
        "tier": TIER_SUPPORTER,
        "title": "Favorite track on profile",
        "description": "Pin a specific lane (RT/CT runner or bagger) as the featured rating on your profile.",
        "status": PERK_STATUS_LIVE,
    },
    {
        "id": "lineup_name_color",
        "tier": TIER_SUPPORTER,
        "title": "Match & chat name color",
        "description": "Custom name color in match lineups and war chat (not on queue boards).",
        "status": PERK_STATUS_LIVE,
    },
    {
        "id": "profile_accent",
        "tier": TIER_SUPPORTER,
        "title": "Profile accent & badge",
        "description": "Accent ring on your avatar, supporter badge, and profile styling.",
        "status": PERK_STATUS_LIVE,
    },
    # --- Supporter (planned) ---
    {
        "id": "discord_role",
        "tier": TIER_SUPPORTER,
        "title": "Discord Supporter role",
        "description": "Automatic Supporter role in linked Discord hub servers.",
        "status": PERK_STATUS_SOON,
    },
    {
        "id": "season_recap_export",
        "tier": TIER_SUPPORTER,
        "title": "Season recap export",
        "description": "Download a shareable card of your SR, lineup stats, and recent wars.",
        "status": PERK_STATUS_SOON,
    },
    {
        "id": "profile_flair",
        "tier": TIER_SUPPORTER,
        "title": "Profile flair",
        "description": "Small Supporter flair on your public profile page.",
        "status": PERK_STATUS_SOON,
    },
    # --- Supporter+ (live) ---
    {
        "id": "profile_alias",
        "tier": TIER_SUPPORTER_PLUS,
        "title": "Vanity profile URL",
        "description": "Claim /u/your-alias so friends can open your profile easily.",
        "status": PERK_STATUS_LIVE,
    },
    # --- Supporter+ (planned) ---
    {
        "id": "discord_role_plus",
        "tier": TIER_SUPPORTER_PLUS,
        "title": "Discord Supporter+ role",
        "description": "Separate Supporter+ role in linked Discord hub servers (in addition to Supporter perks).",
        "status": PERK_STATUS_SOON,
    },
    {
        "id": "profile_flair_plus",
        "tier": TIER_SUPPORTER_PLUS,
        "title": "Profile flair (Supporter+)",
        "description": "Distinct small flair on your public profile — separate from the Supporter flair.",
        "status": PERK_STATUS_SOON,
    },
    {
        "id": "custom_profile_picture",
        "tier": TIER_SUPPORTER_PLUS,
        "title": "Custom profile picture",
        "description": "Upload a custom avatar for the website (separate from your Discord photo).",
        "status": PERK_STATUS_SOON,
    },
    {
        "id": "beta_feature_flags",
        "tier": TIER_SUPPORTER_PLUS,
        "title": "Beta feature access",
        "description": "Early access to new queue, profile, and matchmaking features before general release.",
        "status": PERK_STATUS_SOON,
    },
)


def _parse_id_list(env_key: str) -> set[int]:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            print(f"⚠️ Ignoring invalid {env_key} entry: {part!r}")
    return out


def _env_tier_override(discord_id: int) -> TierOrNone:
    did = int(discord_id)
    if did in _parse_id_list("SUPPORTER_PLUS_DISCORD_IDS"):
        return TIER_SUPPORTER_PLUS
    if did in _parse_id_list("SUPPORTER_DISCORD_IDS"):
        return TIER_SUPPORTER
    return None


def patreon_page_url() -> str | None:
    url = os.getenv("PATREON_PAGE_URL", "").strip()
    return url or None


_DURATION_RE = re.compile(r"^(\d+)(min|s|h|d|w|m)$", re.IGNORECASE)


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def parse_supporter_duration(raw: str) -> datetime:
    """Parse admin duration strings: 1m=month, 7d, 2w, 12h, 30min, 90s."""
    text = str(raw).strip().lower()
    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError(
            "Invalid duration. Use a number + unit: m (month), d, w, h, min, s — e.g. 1m, 30d, 2w."
        )
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if amount <= 0:
        raise ValueError("Duration must be positive.")

    now = datetime.now(timezone.utc)
    if unit == "m":
        return _add_months(now, amount)
    if unit == "min":
        return now + timedelta(minutes=amount)
    if unit == "s":
        return now + timedelta(seconds=amount)
    if unit == "h":
        return now + timedelta(hours=amount)
    if unit == "d":
        return now + timedelta(days=amount)
    if unit == "w":
        return now + timedelta(weeks=amount)
    raise ValueError("Unsupported duration unit.")


def _tier_is_expired(extended: dict[str, Any]) -> bool:
    expires_at = _parse_iso_datetime(extended.get("supporter_expires_at"))
    if expires_at is None:
        return False
    return expires_at <= datetime.now(timezone.utc)


def _clear_expired_tier(discord_id: int, extended: dict[str, Any]) -> None:
    if not _tier_is_expired(extended):
        return
    update_extended_profile_fields(
        int(discord_id),
        supporter_tier=None,
        supporter=False,
        supporter_expires_at=None,
        _internal=True,
    )


def supporter_tier(discord_id: int) -> TierOrNone:
    override = _env_tier_override(discord_id)
    if override:
        return override
    try:
        extended = get_extended_profile_fields(discord_id)
        if _tier_is_expired(extended):
            _clear_expired_tier(discord_id, extended)
            return None
        raw = extended.get("supporter_tier")
        if raw in (TIER_SUPPORTER, TIER_SUPPORTER_PLUS):
            return raw
        if extended.get("supporter"):
            return TIER_SUPPORTER
    except Exception:
        return None
    return None


def has_supporter_tier(discord_id: int, minimum: SupporterTier = TIER_SUPPORTER) -> bool:
    tier = supporter_tier(discord_id)
    if not tier:
        return False
    return TIER_RANK[tier] >= TIER_RANK[minimum]


def is_supporter(discord_id: int) -> bool:
    return has_supporter_tier(discord_id, TIER_SUPPORTER)


def is_supporter_plus(discord_id: int) -> bool:
    return has_supporter_tier(discord_id, TIER_SUPPORTER_PLUS)


def tier_label(tier: TierOrNone) -> str | None:
    if tier == TIER_SUPPORTER_PLUS:
        return "Supporter+"
    if tier == TIER_SUPPORTER:
        return "Supporter"
    return None


def normalize_alias(raw: str) -> str:
    return raw.strip().lower()


def validate_alias(alias: str) -> str | None:
    cleaned = normalize_alias(alias)
    if not cleaned:
        return "Alias cannot be empty."
    if not ALIAS_RE.match(cleaned):
        return "Alias must be 3–32 characters: lowercase letters, numbers, _ or -."
    if cleaned in RESERVED_ALIASES:
        return "That alias is reserved."
    if cleaned.isdigit():
        return "Alias cannot be only numbers (use your Discord profile link instead)."
    return None


def set_supporter_tier(
    discord_id: int,
    tier: TierOrNone,
    *,
    source: str = "admin",
    expires_at: datetime | None = None,
    expires_in: str | None = None,
) -> dict[str, Any]:
    did = int(discord_id)
    if tier and expires_in:
        expires_at = parse_supporter_duration(expires_in)
    if tier is None:
        expires_at = None
    elif source == "patreon":
        expires_at = None

    current = supporter_tier(did)
    extended = get_extended_profile_fields(did)
    current_expires = _parse_iso_datetime(extended.get("supporter_expires_at"))
    if current == tier and expires_at == current_expires:
        return extended

    update_extended_profile_fields(
        did,
        supporter_tier=tier,
        supporter=bool(tier),
        supporter_expires_at=expires_at,
        _internal=True,
    )
    label = tier or "none"
    expiry_note = f", expires={expires_at.isoformat()}" if expires_at else ""
    print(f"Supporter tier set to {label} for discord_id={did} (source={source}{expiry_note})")
    return get_extended_profile_fields(did)


def set_supporter_flag(discord_id: int, active: bool, *, source: str = "patreon") -> dict[str, Any]:
    return set_supporter_tier(
        discord_id,
        TIER_SUPPORTER if active else None,
        source=source,
    )


def pledge_to_tier(pledge_cents: int | None) -> TierOrNone:
    min_base = int(os.getenv("PATREON_MIN_PLEDGE_CENTS", "100"))
    min_plus = int(os.getenv("PATREON_SUPPORTER_PLUS_MIN_CENTS", "500"))
    if pledge_cents is None:
        return TIER_SUPPORTER
    if pledge_cents >= min_plus:
        return TIER_SUPPORTER_PLUS
    if pledge_cents >= min_base:
        return TIER_SUPPORTER
    return None


def perks_for_tier(tier: TierOrNone) -> list[dict[str, Any]]:
    if not tier:
        return []
    rank = TIER_RANK[tier]
    return [perk for perk in PUBLIC_PERK_CATALOG if TIER_RANK[perk["tier"]] <= rank]


def public_perks_payload() -> dict[str, Any]:
    return {
        "tiers": [
            {
                "id": TIER_SUPPORTER,
                "label": "Supporter",
                "perks": [p for p in PUBLIC_PERK_CATALOG if p["tier"] == TIER_SUPPORTER],
            },
            {
                "id": TIER_SUPPORTER_PLUS,
                "label": "Supporter+",
                "includes": TIER_SUPPORTER,
                "perks": [p for p in PUBLIC_PERK_CATALOG if p["tier"] == TIER_SUPPORTER_PLUS],
            },
        ],
        "patreon_page_url": patreon_page_url(),
    }


def supporter_status_payload(discord_id: int) -> dict[str, Any]:
    from api.services.patreon_membership import get_membership_for_discord

    extended = get_extended_profile_fields(discord_id)
    membership = get_membership_for_discord(discord_id)
    tier = supporter_tier(discord_id)
    env_override = _env_tier_override(discord_id)
    if env_override:
        source = "env_override"
    elif membership:
        source = "patreon"
    elif tier:
        source = "admin"
    else:
        source = "none"

    return {
        "active": tier is not None,
        "tier": tier,
        "tier_label": tier_label(tier),
        "supporter": tier is not None,
        "source": source,
        "perks": perks_for_tier(tier),
        "catalog": public_perks_payload(),
        "patreon_page_url": patreon_page_url(),
        "membership": membership,
        "supporter_expires_at": extended.get("supporter_expires_at") if tier else None,
        "accent_color": extended.get("accent_color") if tier else None,
        "lineup_name_color": extended.get("lineup_name_color") if tier else None,
        "favorite_track": extended.get("favorite_track") if tier else None,
        "profile_alias": extended.get("profile_alias") if tier == TIER_SUPPORTER_PLUS else None,
        "display_name_custom": bool(extended.get("display_name_custom")),
    }


def _patron_display_name(extended: dict[str, Any], discord_id: int) -> str:
    name = (extended.get("display_name") or extended.get("discord_username") or "").strip()
    return name or str(discord_id)


def _patron_profile_path(extended: dict[str, Any], discord_id: int) -> str:
    alias = (extended.get("profile_alias") or "").strip()
    if alias:
        return f"/u/{alias}"
    return f"/u/{discord_id}"


def list_public_patrons(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    if use_json_stores():
        from utils.player_profile_store import _load_all

        patrons: list[dict[str, Any]] = []
        for key in (_load_all().get("profiles") or {}).keys():
            try:
                did = int(key)
            except (TypeError, ValueError):
                continue
            extended = get_extended_profile_fields(did)
            tier = extended.get("supporter_tier") or (TIER_SUPPORTER if extended.get("supporter") else None)
            if not tier:
                continue
            patrons.append(
                {
                    "discord_id": str(did),
                    "display_name": _patron_display_name(extended, did),
                    "tier": tier,
                    "tier_label": tier_label(tier),
                    "profile_path": _patron_profile_path(extended, did),
                }
            )
        patrons.sort(key=lambda row: (row["tier"] != TIER_SUPPORTER_PLUS, row["display_name"].lower()))
        return patrons[:limit]

    patrons = []
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT discord_id, display_name, discord_username, profile_alias, supporter_tier, supporter
                    FROM players
                    WHERE supporter_tier IN ('supporter', 'supporter_plus')
                       OR supporter = TRUE
                    ORDER BY
                      CASE supporter_tier
                        WHEN 'supporter_plus' THEN 0
                        WHEN 'supporter' THEN 1
                        ELSE 2
                      END,
                      LOWER(COALESCE(display_name, discord_username, discord_id::text))
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ list_public_patrons failed: {exc}")
        return []

    for row in rows:
        did = int(row[0])
        extended = {
            "display_name": row[1],
            "discord_username": row[2],
            "profile_alias": row[3],
            "supporter_tier": row[4] if row[4] in (TIER_SUPPORTER, TIER_SUPPORTER_PLUS) else None,
            "supporter": bool(row[5]),
        }
        tier = extended.get("supporter_tier") or (TIER_SUPPORTER if extended.get("supporter") else None)
        if not tier:
            continue
        patrons.append(
            {
                "discord_id": str(did),
                "display_name": _patron_display_name(extended, did),
                "tier": tier,
                "tier_label": tier_label(tier),
                "profile_path": _patron_profile_path(extended, did),
            }
        )
    return patrons
