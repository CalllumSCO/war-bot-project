"""Queue parties — Postgres queue_parties or temp/queue-parties.json."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

QUEUE_STORE_PATH = os.path.join(DATA_DIR, "queue-parties.json")


def _parse(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(QUEUE_STORE_PATH):
        return {"parties": {}}
    try:
        with open(QUEUE_STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "parties" in data else {"parties": {}}
    except json.JSONDecodeError:
        return {"parties": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(QUEUE_STORE_PATH), exist_ok=True)
    with open(QUEUE_STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def list_parties() -> List[Dict[str, Any]]:
    if use_json_stores():
        return list(_load_all()["parties"].values())
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT data FROM queue_parties")
            rows = cursor.fetchall()
        finally:
            cursor.close()
    return [_parse(r[0]) for r in rows]


def get_party(party_id: str) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["parties"].get(party_id)
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT data FROM queue_parties WHERE party_id = %s", (party_id,))
            row = cursor.fetchone()
        finally:
            cursor.close()
    return _parse(row[0]) if row else None


def get_party_by_invite(invite_code: str) -> Optional[Dict[str, Any]]:
    for party in list_parties():
        if party.get("invite_code") == invite_code and party.get("status") == "preparing":
            return party
    return None


def _discord_ids_equal(left: Any, right: Any) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right and left is not None


def get_active_party_for_user(discord_id: int) -> Optional[Dict[str, Any]]:
    """Return the active party that includes this user in its lineup (preferred)."""
    for party in list_parties():
        if party.get("status") not in ("preparing", "posted", "matched"):
            continue
        for player in party.get("lineup", []):
            if _discord_ids_equal(player.get("discord_id"), discord_id):
                return party
    # Fallback: captain of a party with a desynced/empty lineup still owns it.
    for party in list_parties():
        if party.get("status") not in ("preparing", "posted", "matched"):
            continue
        if _discord_ids_equal(party.get("captain_discord_id"), discord_id):
            return party
    return None


def get_active_party_for_guild(guild_id: int) -> Optional[Dict[str, Any]]:
    for party in list_parties():
        if party.get("guild_id") == guild_id and party.get("status") in (
            "preparing",
            "posted",
            "matched",
        ):
            return party
    return None


def upsert_party(party: Dict[str, Any]) -> Dict[str, Any]:
    party["last_updated"] = datetime.utcnow().isoformat()
    if use_json_stores():
        data = _load_all()
        data["parties"][party["party_id"]] = party
        _save_all(data)
        return party
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO queue_parties (
                  party_id, invite_code, captain_discord_id, guild_id, data, status, updated_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, NOW())
                ON CONFLICT (party_id) DO UPDATE SET
                  invite_code = EXCLUDED.invite_code,
                  captain_discord_id = EXCLUDED.captain_discord_id,
                  guild_id = EXCLUDED.guild_id,
                  data = EXCLUDED.data,
                  status = EXCLUDED.status,
                  updated_at = NOW()
                """,
                (
                    party["party_id"],
                    party.get("invite_code"),
                    party.get("captain_discord_id"),
                    party.get("guild_id"),
                    json.dumps(party),
                    party.get("status"),
                ),
            )
        finally:
            cursor.close()
    return party


def delete_party(party_id: str) -> bool:
    if use_json_stores():
        data = _load_all()
        if party_id not in data["parties"]:
            return False
        del data["parties"][party_id]
        _save_all(data)
        return True
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM queue_parties WHERE party_id = %s", (party_id,))
            return cursor.rowcount > 0
        finally:
            cursor.close()
