"""Party invites (SendouQ-style Invite) — Postgres or temp/party-invites.json."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

STORE_PATH = os.path.join(DATA_DIR, "party-invites.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(STORE_PATH):
        return {"invites": {}}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "invites" in data else {"invites": {}}
    except json.JSONDecodeError:
        return {"invites": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def get_party_invite(invite_id: str) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["invites"].get(invite_id)
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT data FROM party_invites WHERE invite_id = %s",
                (invite_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if not row:
        return None
    data = row[0]
    return json.loads(data) if isinstance(data, str) else data


def upsert_party_invite(invite: Dict[str, Any]) -> Dict[str, Any]:
    invite.setdefault("invite_id", str(uuid.uuid4()))
    invite.setdefault("status", "pending")
    invite["updated_at"] = datetime.utcnow().isoformat()
    if use_json_stores():
        data = _load_all()
        data["invites"][invite["invite_id"]] = invite
        _save_all(data)
        return invite
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO party_invites (
                  invite_id, party_id, from_discord_id, target_discord_id, status, data, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (invite_id) DO UPDATE SET
                  status = EXCLUDED.status,
                  data = EXCLUDED.data,
                  updated_at = NOW()
                """,
                (
                    invite["invite_id"],
                    invite["party_id"],
                    int(invite["from_discord_id"]),
                    int(invite["target_discord_id"]),
                    invite.get("status", "pending"),
                    json.dumps(invite),
                ),
            )
        finally:
            cursor.close()
    return invite


def delete_party_invite(invite_id: str) -> bool:
    if use_json_stores():
        data = _load_all()
        if invite_id not in data["invites"]:
            return False
        del data["invites"][invite_id]
        _save_all(data)
        return True
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM party_invites WHERE invite_id = %s", (invite_id,))
            return cursor.rowcount > 0
        finally:
            cursor.close()


def create_party_invite(
    party_id: str,
    from_discord_id: int,
    target_discord_id: int,
) -> Dict[str, Any]:
    return upsert_party_invite(
        {
            "invite_id": str(uuid.uuid4()),
            "party_id": party_id,
            "from_discord_id": int(from_discord_id),
            "target_discord_id": int(target_discord_id),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
    )


def list_outbound_invites(party_id: str) -> List[Dict[str, Any]]:
    if use_json_stores():
        return [
            i
            for i in _load_all()["invites"].values()
            if i.get("party_id") == party_id and i.get("status") == "pending"
        ]
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT data FROM party_invites
                WHERE party_id = %s AND status = 'pending'
                """,
                (party_id,),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    out = []
    for (data,) in rows:
        out.append(json.loads(data) if isinstance(data, str) else data)
    return out


def list_inbound_invites(discord_id: int) -> List[Dict[str, Any]]:
    if use_json_stores():
        return [
            i
            for i in _load_all()["invites"].values()
            if i.get("target_discord_id") == int(discord_id) and i.get("status") == "pending"
        ]
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT data FROM party_invites
                WHERE target_discord_id = %s AND status = 'pending'
                """,
                (int(discord_id),),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    return [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in rows]
