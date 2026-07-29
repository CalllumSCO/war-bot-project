"""Player profile / FC link — Postgres `players` or temp/player-profiles.json."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

PROFILE_STORE_PATH = os.path.join(DATA_DIR, "player-profiles.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(PROFILE_STORE_PATH):
        return {"profiles": {}}
    try:
        with open(PROFILE_STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "profiles" in data else {"profiles": {}}
    except json.JSONDecodeError:
        return {"profiles": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PROFILE_STORE_PATH), exist_ok=True)
    with open(PROFILE_STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _row_to_profile(row: tuple) -> Dict[str, Any]:
    (
        discord_id,
        friend_code,
        lounge_name,
        lounge_player_id,
        link_source,
        lounge_verified,
        last_fc_verified_at,
        updated_at,
    ) = row
    profile: Dict[str, Any] = {"discord_id": int(discord_id)}
    if friend_code:
        profile["friend_code"] = friend_code
    if lounge_name:
        profile["lounge_name"] = lounge_name
    if lounge_player_id is not None:
        profile["lounge_player_id"] = int(lounge_player_id)
    if link_source:
        profile["link_source"] = link_source
    profile["lounge_verified"] = bool(lounge_verified)
    if last_fc_verified_at is not None:
        profile["last_fc_verified_at"] = (
            last_fc_verified_at.isoformat()
            if hasattr(last_fc_verified_at, "isoformat")
            else str(last_fc_verified_at)
        )
    if updated_at is not None:
        profile["updated_at"] = (
            updated_at.isoformat()
            if hasattr(updated_at, "isoformat")
            else str(updated_at)
        )
    return profile


def get_profile(discord_id: int) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["profiles"].get(str(discord_id))

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT discord_id, friend_code, lounge_name, lounge_player_id,
                       link_source, lounge_verified, last_fc_verified_at, updated_at
                FROM players WHERE discord_id = %s
                """,
                (int(discord_id),),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if not row:
        return None
    profile = _row_to_profile(row)
    # Match JSON behavior: missing profile key vs empty shell — treat no FC and
    # no lounge fields as absent only if the row was MMR-only with nothing else.
    if not profile.get("friend_code") and not profile.get("lounge_name") and not profile.get(
        "link_source"
    ):
        # Still return the row if it exists so callers can update; JSON returned
        # None only when key missing. Prefer returning profile when row exists.
        pass
    return profile


def upsert_profile(discord_id: int, **fields: Any) -> Dict[str, Any]:
    if use_json_stores():
        data = _load_all()
        key = str(discord_id)
        current = data["profiles"].get(key, {"discord_id": discord_id})
        current.update(fields)
        current["discord_id"] = discord_id
        current["updated_at"] = datetime.utcnow().isoformat()
        data["profiles"][key] = current
        _save_all(data)
        return current

    existing = get_profile(discord_id) or {"discord_id": discord_id}
    existing.update(fields)
    existing["discord_id"] = discord_id

    friend_code = existing.get("friend_code")
    lounge_name = existing.get("lounge_name")
    lounge_player_id = existing.get("lounge_player_id")
    link_source = existing.get("link_source")
    lounge_verified = bool(existing.get("lounge_verified", False))
    last_fc_verified_at = existing.get("last_fc_verified_at")

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO players (
                  discord_id, friend_code, lounge_name, lounge_player_id,
                  link_source, lounge_verified, last_fc_verified_at, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT (discord_id) DO UPDATE SET
                  friend_code = COALESCE(EXCLUDED.friend_code, players.friend_code),
                  lounge_name = COALESCE(EXCLUDED.lounge_name, players.lounge_name),
                  lounge_player_id = COALESCE(EXCLUDED.lounge_player_id, players.lounge_player_id),
                  link_source = COALESCE(EXCLUDED.link_source, players.link_source),
                  lounge_verified = EXCLUDED.lounge_verified,
                  last_fc_verified_at = COALESCE(
                    EXCLUDED.last_fc_verified_at, players.last_fc_verified_at
                  ),
                  updated_at = NOW()
                """,
                (
                    int(discord_id),
                    friend_code,
                    lounge_name,
                    int(lounge_player_id) if lounge_player_id is not None else None,
                    link_source,
                    lounge_verified,
                    last_fc_verified_at,
                ),
            )
        finally:
            cursor.close()

    existing["updated_at"] = datetime.utcnow().isoformat()
    return existing


def has_linked_fc(discord_id: int) -> bool:
    profile = get_profile(discord_id)
    return bool(profile and profile.get("friend_code"))
