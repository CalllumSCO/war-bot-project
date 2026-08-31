"""Display enrichment for match lineups and chat (not queue boards)."""

from __future__ import annotations

from typing import Any

from api.services.profile_fields import get_extended_profile_fields, get_extended_profile_fields_many
from api.services.supporter import is_supporter


def enrich_lineup_entry_for_match(
    entry: dict[str, Any],
    *,
    profiles: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out = dict(entry)
    discord_id = entry.get("discord_id")
    if discord_id is None:
        return out
    try:
        did = int(discord_id)
        out["discord_id"] = str(did)
    except (TypeError, ValueError):
        out["discord_id"] = str(discord_id)
        return out

    extended = (profiles or {}).get(did)
    if extended is None:
        extended = get_extended_profile_fields(did)
    if extended.get("discord_avatar_url"):
        out["avatar"] = extended["discord_avatar_url"]
    if extended.get("display_name"):
        out["player"] = extended["display_name"]
    if is_supporter(did):
        color = extended.get("lineup_name_color") or extended.get("chat_name_color")
        if color:
            out["name_color"] = color
    return out


def enrich_lineup_for_match(
    lineup: list[dict[str, Any]] | None,
    *,
    profiles: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not lineup:
        return []
    ids: list[int] = []
    for entry in lineup:
        try:
            if entry.get("discord_id") is not None:
                ids.append(int(entry["discord_id"]))
        except (TypeError, ValueError):
            continue
    batch = profiles if profiles is not None else get_extended_profile_fields_many(ids)
    return [enrich_lineup_entry_for_match(entry, profiles=batch) for entry in lineup]


def author_name_color(discord_id: int | None) -> str | None:
    if discord_id is None or not is_supporter(discord_id):
        return None
    extended = get_extended_profile_fields(int(discord_id))
    return extended.get("lineup_name_color") or extended.get("chat_name_color")
