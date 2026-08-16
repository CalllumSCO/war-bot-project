"""
Read/write helpers for the schema_v2 profile-cosmetics columns on `players`
(bio, mkc_url, lounge_url, socials, discord_avatar_url, discord_username,
display_name, supporter, accent_color, chat_name_color).

`utils.player_profile_store` only persists the friend-code/lounge link
columns to Postgres, so these extra fields are handled here directly. This
module never touches player_profile_store.py itself (a plan file) — it only
reads/writes the `players` table (or, in JSON-store mode, reuses
upsert_profile, which already accepts arbitrary keys).

Every DB call is wrapped defensively so a missing schema_v2 migration or an
unreachable database degrades to empty/default values instead of crashing
the API.
"""

from __future__ import annotations

from typing import Any

from utils.db import get_conn, use_json_stores
from utils.player_profile_store import get_profile, upsert_profile

EXTENDED_FIELDS: tuple[str, ...] = (
    "bio",
    "mkc_url",
    "lounge_url",
    "x_url",
    "bluesky_url",
    "youtube_url",
    "twitch_url",
    "discord_avatar_url",
    "discord_username",
    "display_name",
    "supporter",
    "accent_color",
    "chat_name_color",
)

# User-editable fields that may be explicitly cleared with null.
CLEARABLE_FIELDS = frozenset(
    {
        "bio",
        "mkc_url",
        "lounge_url",
        "x_url",
        "bluesky_url",
        "youtube_url",
        "twitch_url",
        "accent_color",
        "chat_name_color",
    }
)


def _defaults() -> dict[str, Any]:
    return {field: (False if field == "supporter" else None) for field in EXTENDED_FIELDS}


def get_extended_profile_fields(discord_id: int) -> dict[str, Any]:
    """Best-effort read of the cosmetic profile fields for a Discord user."""
    if use_json_stores():
        profile = get_profile(discord_id) or {}
        result = _defaults()
        for field in EXTENDED_FIELDS:
            if field in profile:
                result[field] = profile[field]
        result["supporter"] = bool(result.get("supporter"))
        return result

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"""
                    SELECT {", ".join(EXTENDED_FIELDS)}
                    FROM players WHERE discord_id = %s
                    """,
                    (int(discord_id),),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
    except Exception as exc:  # missing schema_v2 columns / unreachable DB
        print(f"⚠️ get_extended_profile_fields fallback for {discord_id}: {exc}")
        return _defaults()

    if not row:
        return _defaults()

    result = dict(zip(EXTENDED_FIELDS, row))
    result["supporter"] = bool(result.get("supporter"))
    return result


def get_extended_profile_fields_many(discord_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Batch read of cosmetic fields — one query for many discord ids."""
    unique: list[int] = []
    seen: set[int] = set()
    for raw in discord_ids:
        try:
            did = int(raw)
        except (TypeError, ValueError):
            continue
        if did in seen:
            continue
        seen.add(did)
        unique.append(did)
    if not unique:
        return {}

    if use_json_stores():
        return {did: get_extended_profile_fields(did) for did in unique}

    out: dict[int, dict[str, Any]] = {did: _defaults() for did in unique}
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"""
                    SELECT discord_id, {", ".join(EXTENDED_FIELDS)}
                    FROM players WHERE discord_id = ANY(%s)
                    """,
                    (unique,),
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ get_extended_profile_fields_many fallback: {exc}")
        return {did: get_extended_profile_fields(did) for did in unique}

    for row in rows:
        did = int(row[0])
        result = dict(zip(EXTENDED_FIELDS, row[1:]))
        result["supporter"] = bool(result.get("supporter"))
        out[did] = result
    return out


def update_extended_profile_fields(discord_id: int, **fields: Any) -> dict[str, Any]:
    """Best-effort write of a subset of the cosmetic profile fields."""
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in EXTENDED_FIELDS:
            continue
        if value is None and key not in CLEARABLE_FIELDS:
            continue
        cleaned[key] = value
    if not cleaned:
        return get_extended_profile_fields(discord_id)

    if use_json_stores():
        upsert_profile(discord_id, **cleaned)
        return get_extended_profile_fields(discord_id)

    columns = list(cleaned.keys())
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                insert_cols = ["discord_id", *columns]
                placeholders = ", ".join(["%s"] * len(insert_cols))
                set_clause = ", ".join(f"{col} = EXCLUDED.{col}" for col in columns)
                cursor.execute(
                    f"""
                    INSERT INTO players ({", ".join(insert_cols)}, updated_at)
                    VALUES ({placeholders}, NOW())
                    ON CONFLICT (discord_id) DO UPDATE SET {set_clause}, updated_at = NOW()
                    """,
                    [int(discord_id), *[cleaned[c] for c in columns]],
                )
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ update_extended_profile_fields failed for {discord_id}: {exc}")
        return get_extended_profile_fields(discord_id)

    return get_extended_profile_fields(discord_id)


def is_supporter(discord_id: int) -> bool:
    try:
        return bool(get_extended_profile_fields(discord_id).get("supporter"))
    except Exception:
        return False
