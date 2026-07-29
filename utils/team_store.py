"""Team store — Postgres `teams` or temp/teams.json."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

TEAM_STORE_PATH = os.path.join(DATA_DIR, "teams.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(TEAM_STORE_PATH):
        return {"teams": {}}
    try:
        with open(TEAM_STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "teams" in data else {"teams": {}}
    except json.JSONDecodeError:
        return {"teams": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(TEAM_STORE_PATH), exist_ok=True)
    with open(TEAM_STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _parse_data(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def get_team_by_guild(guild_id: int) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["teams"].get(str(guild_id))

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT data FROM teams WHERE guild_id = %s",
                (int(guild_id),),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if not row:
        return None
    return _parse_data(row[0])


def upsert_team(team: Dict[str, Any]) -> Dict[str, Any]:
    if use_json_stores():
        data = _load_all()
        key = str(team["guild_id"])
        data["teams"][key] = team
        _save_all(data)
        return team

    guild_id = int(team["guild_id"])
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO teams (guild_id, data, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (guild_id) DO UPDATE SET
                  data = EXCLUDED.data,
                  updated_at = NOW()
                """,
                (guild_id, json.dumps(team)),
            )
        finally:
            cursor.close()
    return team
