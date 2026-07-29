"""Pending Discord guild joins for auto-invited allies (role grant on MemberAdd)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from utils.config import DATA_DIR

STORE_PATH = os.path.join(DATA_DIR, "pending-ally-joins.json")
TTL_HOURS = 24


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(STORE_PATH):
        return {"pending": {}}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "pending" in data else {"pending": {}}
    except json.JSONDecodeError:
        return {"pending": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def remember_pending_ally_join(
    discord_id: int,
    guild_id: int,
    ally_role_id: int,
    *,
    team_name: str | None = None,
) -> None:
    entry = {
        "discord_id": int(discord_id),
        "guild_id": int(guild_id),
        "ally_role_id": int(ally_role_id),
        "team_name": team_name,
        "expires_at": (datetime.utcnow() + timedelta(hours=TTL_HOURS)).isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }
    key = str(int(discord_id))
    data = _load_all()
    data["pending"][key] = entry
    _save_all(data)


def pop_pending_ally_join(discord_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
    key = str(int(discord_id))
    data = _load_all()
    entry = data["pending"].get(key)
    if not entry:
        return None
    try:
        if int(entry.get("guild_id") or 0) != int(guild_id):
            return None
    except (TypeError, ValueError):
        return None

    expires = entry.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.utcnow():
                del data["pending"][key]
                _save_all(data)
                return None
        except ValueError:
            pass

    del data["pending"][key]
    _save_all(data)
    return entry
