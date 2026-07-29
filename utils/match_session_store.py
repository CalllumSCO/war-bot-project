"""Match sessions — Postgres match_sessions or temp/match-sessions.json."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

MATCH_SESSIONS_PATH = os.path.join(DATA_DIR, "match-sessions.json")


def _parse(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(MATCH_SESSIONS_PATH):
        return {"sessions": {}}
    try:
        with open(MATCH_SESSIONS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "sessions" in data else {"sessions": {}}
    except json.JSONDecodeError:
        return {"sessions": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(MATCH_SESSIONS_PATH), exist_ok=True)
    with open(MATCH_SESSIONS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _all_sessions() -> List[Dict[str, Any]]:
    if use_json_stores():
        return list(_load_all()["sessions"].values())
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT data FROM match_sessions")
            rows = cursor.fetchall()
        finally:
            cursor.close()
    return [_parse(r[0]) for r in rows]


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["sessions"].get(session_id)
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT data FROM match_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    return _parse(row[0]) if row else None


def get_session_by_channel(channel_id: int) -> Optional[Dict[str, Any]]:
    for session in _all_sessions():
        if channel_id in (
            session.get("channel_a_id"),
            session.get("channel_b_id"),
        ):
            return session
    return None


def get_session_by_war_id(war_id: str) -> Optional[Dict[str, Any]]:
    for session in _all_sessions():
        if war_id in (session.get("war_a_id"), session.get("war_b_id")):
            return session
    return None


def get_session_for_user(discord_id: int) -> Optional[Dict[str, Any]]:
    did = int(discord_id)
    for session in _all_sessions():
        if did in [int(x) for x in session.get("roster_a_ids", [])] or did in [
            int(x) for x in session.get("roster_b_ids", [])
        ]:
            return session
    return None


def delete_session(session_id: str) -> bool:
    if use_json_stores():
        data = _load_all()
        if session_id not in data["sessions"]:
            return False
        del data["sessions"][session_id]
        _save_all(data)
        return True
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM match_sessions WHERE session_id = %s", (session_id,))
            return cursor.rowcount > 0
        finally:
            cursor.close()


def upsert_session(session: Dict[str, Any]) -> Dict[str, Any]:
    if use_json_stores():
        data = _load_all()
        data["sessions"][session["session_id"]] = session
        _save_all(data)
        return session
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO match_sessions (session_id, data, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (session_id) DO UPDATE SET
                  data = EXCLUDED.data,
                  updated_at = NOW()
                """,
                (session["session_id"], json.dumps(session)),
            )
        finally:
            cursor.close()
    return session


def create_session(
    board: str,
    war_a: Dict[str, Any],
    war_b: Dict[str, Any],
    channel_a_id: int,
    channel_b_id: int,
    roster_a_ids: List[int],
    roster_b_ids: List[int],
) -> Dict[str, Any]:
    session = {
        "session_id": str(uuid.uuid4()),
        "board": board,
        "war_a_id": war_a.get("war_id"),
        "war_b_id": war_b.get("war_id"),
        "guild_a_id": war_a.get("origin_guild_id"),
        "guild_b_id": war_b.get("origin_guild_id"),
        "team_a_name": war_a.get("team_name"),
        "team_b_name": war_b.get("team_name"),
        "lineup_a": war_a.get("lineup") or [],
        "lineup_b": war_b.get("lineup") or [],
        "channel_a_id": channel_a_id,
        "channel_b_id": channel_b_id,
        "roster_a_ids": roster_a_ids,
        "roster_b_ids": roster_b_ids,
        "created_at": datetime.utcnow().isoformat(),
    }
    return upsert_session(session)
