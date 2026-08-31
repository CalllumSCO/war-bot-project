"""Resolve public profile identifiers (Discord snowflake or Supporter+ alias)."""

from __future__ import annotations

from api.services.profile_fields import get_extended_profile_fields
from utils.db import get_conn, use_json_stores


def resolve_profile_identifier(identifier: str) -> int | None:
    raw = (identifier or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)

    alias = raw.lower()
    if use_json_stores():
        from utils.player_profile_store import _load_all

        for key in (_load_all().get("profiles") or {}).keys():
            try:
                did = int(key)
            except (TypeError, ValueError):
                continue
            extended = get_extended_profile_fields(did)
            stored = (extended.get("profile_alias") or "").strip().lower()
            if stored and stored == alias:
                return did
        return None

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT discord_id FROM players
                    WHERE LOWER(profile_alias) = %s
                    LIMIT 1
                    """,
                    (alias,),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ resolve_profile_identifier failed for {alias!r}: {exc}")
        return None

    return int(row[0]) if row else None
