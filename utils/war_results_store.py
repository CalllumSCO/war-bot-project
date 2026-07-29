"""War results — Postgres `war_results` or temp/war-results.json."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

WAR_RESULTS_PATH = os.path.join(DATA_DIR, "war-results.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(WAR_RESULTS_PATH):
        return {"results": []}
    try:
        with open(WAR_RESULTS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "results" in data else {"results": []}
    except json.JSONDecodeError:
        return {"results": []}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(WAR_RESULTS_PATH), exist_ok=True)
    with open(WAR_RESULTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _parse_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def append_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result.setdefault("result_id", str(uuid.uuid4()))
    result.setdefault("completed_at", datetime.utcnow().isoformat())
    result.setdefault("table_bot_synced", False)

    if use_json_stores():
        data = _load_all()
        data["results"].append(result)
        _save_all(data)
        return result

    completed_at = result.get("completed_at")
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO war_results (result_id, completed_at, payload)
                VALUES (%s, %s::timestamptz, %s::jsonb)
                ON CONFLICT (result_id) DO UPDATE SET
                  completed_at = EXCLUDED.completed_at,
                  payload = EXCLUDED.payload
                """,
                (
                    result["result_id"],
                    completed_at,
                    json.dumps(result),
                ),
            )
        finally:
            cursor.close()
    return result


def list_results() -> List[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["results"]

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT payload FROM war_results
                ORDER BY completed_at ASC, id ASC
                """
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    return [_parse_payload(row[0]) for row in rows]


def get_result(result_id: str) -> Dict[str, Any] | None:
    rid = str(result_id)
    if use_json_stores():
        for result in _load_all()["results"]:
            if str(result.get("result_id")) == rid:
                return result
        return None

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT payload FROM war_results WHERE result_id = %s LIMIT 1",
                (rid,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if not row:
        return None
    return _parse_payload(row[0])


def list_results_for_player(discord_id: int, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Most recent completed wars involving this Discord user (newest first)."""
    matches: List[Dict[str, Any]] = []
    target = int(discord_id)
    for result in reversed(list_results()):
        found_side = None
        found_player = None
        for side, key in (("winner", "winner_lineup"), ("loser", "loser_lineup")):
            for player in result.get(key) or []:
                if int(player.get("discord_id") or 0) == target:
                    found_side = side
                    found_player = player
                    break
            if found_side:
                break
        if not found_side:
            continue
        matches.append(
            {
                **result,
                "player_outcome": "W" if found_side == "winner" else "L",
                "player_entry": found_player,
            }
        )
        if len(matches) >= limit:
            break
    return matches
