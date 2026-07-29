"""Guild config — Postgres `guild_configs` or temp/guild-config.json."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from utils.boards import ALL_BOARD_KEYS, parse_board_key
from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

GUILD_CONFIG_PATH = os.path.join(DATA_DIR, "guild-config.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(GUILD_CONFIG_PATH):
        return {"guilds": {}}
    try:
        with open(GUILD_CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if "guilds" not in data:
                return {"guilds": {}}
            return data
    except json.JSONDecodeError:
        return {"guilds": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(GUILD_CONFIG_PATH), exist_ok=True)
    with open(GUILD_CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _parse_data(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _all_guilds() -> Dict[str, Dict[str, Any]]:
    if use_json_stores():
        return _load_all().get("guilds", {})

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT guild_id, guild_name, data FROM guild_configs")
            rows = cursor.fetchall()
        finally:
            cursor.close()

    guilds: Dict[str, Dict[str, Any]] = {}
    for guild_id, guild_name, data in rows:
        config = _parse_data(data)
        config["guild_id"] = int(guild_id)
        if guild_name and not config.get("name"):
            config["name"] = guild_name
        guilds[str(guild_id)] = config
    return guilds


def get_guild_config(guild_id: int) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["guilds"].get(str(guild_id))

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT guild_id, guild_name, data FROM guild_configs WHERE guild_id = %s",
                (int(guild_id),),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if not row:
        return None
    config = _parse_data(row[2])
    config["guild_id"] = int(row[0])
    if row[1] and not config.get("name"):
        config["name"] = row[1]
    return config


def upsert_guild_config(guild_id: int, guild_name: str, **fields) -> Dict[str, Any]:
    current = get_guild_config(guild_id) or {}
    current.update(fields)
    current["guild_id"] = guild_id
    current["name"] = guild_name

    if use_json_stores():
        data = _load_all()
        data["guilds"][str(guild_id)] = current
        _save_all(data)
        return current

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO guild_configs (guild_id, guild_name, data, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (guild_id) DO UPDATE SET
                  guild_name = EXCLUDED.guild_name,
                  data = EXCLUDED.data,
                  updated_at = NOW()
                """,
                (int(guild_id), guild_name, json.dumps(current)),
            )
        finally:
            cursor.close()
    return current


def delete_guild_config(guild_id: int) -> bool:
    if use_json_stores():
        data = _load_all()
        key = str(guild_id)
        if key not in data["guilds"]:
            return False
        del data["guilds"][key]
        _save_all(data)
        return True

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM guild_configs WHERE guild_id = %s",
                (int(guild_id),),
            )
            deleted = cursor.rowcount > 0
        finally:
            cursor.close()
    return deleted


def _board_channel_field(board: str) -> str:
    war_type, mode = parse_board_key(board)
    prefix = "ct" if war_type == "CT" else "rt"
    return f"{prefix}_{mode}_channel_id"


def list_billboard_channel_targets(board: str) -> list[Dict[str, Any]]:
    """Return guild + channel pairs for a board (one entry per unique channel)."""
    targets: list[Dict[str, Any]] = []
    seen_channels: set[int] = set()
    field = _board_channel_field(board)
    war_type, mode = parse_board_key(board)
    legacy_field = "ct_channel_id" if war_type == "CT" else "rt_channel_id"

    for config in _all_guilds().values():
        guild_id = config.get("guild_id")
        channel_id = config.get(field)
        if not channel_id and mode == "ranked":
            channel_id = config.get(legacy_field)
        if not guild_id or not channel_id:
            continue

        channel_id = int(channel_id)
        if channel_id in seen_channels:
            continue
        seen_channels.add(channel_id)
        targets.append(
            {
                "guild_id": int(guild_id),
                "channel_id": channel_id,
                "guild_name": config.get("name", str(guild_id)),
            }
        )
    return targets


def list_configured_billboard_channels(board: str) -> list[int]:
    return [target["channel_id"] for target in list_billboard_channel_targets(board)]


def get_billboard_channel_id(guild_id: Optional[int], board: str) -> Optional[int]:
    if guild_id:
        config = get_guild_config(guild_id)
        if config:
            field = _board_channel_field(board)
            channel_id = config.get(field)
            if not channel_id:
                war_type, mode = parse_board_key(board)
                if mode == "ranked":
                    legacy = "ct_channel_id" if war_type == "CT" else "rt_channel_id"
                    channel_id = config.get(legacy)
            if channel_id:
                return int(channel_id)
    return None


def list_all_billboard_channel_ids() -> list[int]:
    ids = []
    for board in ALL_BOARD_KEYS:
        for channel_id in list_configured_billboard_channels(board):
            if channel_id not in ids:
                ids.append(channel_id)
    return ids


def get_queue_channel_id(guild_id: int) -> Optional[int]:
    config = get_guild_config(guild_id)
    if config and config.get("queue_channel_id"):
        return int(config["queue_channel_id"])
    return None


def is_auto_invite_allies_enabled(config: Optional[Dict[str, Any]]) -> bool:
    """Default ON unless explicitly disabled in guild config."""
    if not config:
        return False  # no setup → nothing to invite into
    if "auto_invite_allies" not in config:
        return True
    return bool(config.get("auto_invite_allies"))
