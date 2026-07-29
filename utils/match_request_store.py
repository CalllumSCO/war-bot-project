"""Match requests — Postgres match_requests or temp/match-requests.json."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

MATCH_REQUESTS_PATH = os.path.join(DATA_DIR, "match-requests.json")


def _parse(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(MATCH_REQUESTS_PATH):
        return {"requests": {}}
    try:
        with open(MATCH_REQUESTS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "requests" in data else {"requests": {}}
    except json.JSONDecodeError:
        return {"requests": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(MATCH_REQUESTS_PATH), exist_ok=True)
    with open(MATCH_REQUESTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _all_requests() -> Dict[str, Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["requests"]
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT request_id, data FROM match_requests")
            rows = cursor.fetchall()
        finally:
            cursor.close()
    return {str(r[0]): _parse(r[1]) for r in rows}


def get_request(request_id: str) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["requests"].get(request_id)
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT data FROM match_requests WHERE request_id = %s",
                (request_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    return _parse(row[0]) if row else None


def upsert_request(request: Dict[str, Any]) -> Dict[str, Any]:
    if use_json_stores():
        data = _load_all()
        data["requests"][request["request_id"]] = request
        _save_all(data)
        return request
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO match_requests (
                  request_id, target_war_id, requester_war_id, status, data, updated_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (request_id) DO UPDATE SET
                  target_war_id = EXCLUDED.target_war_id,
                  requester_war_id = EXCLUDED.requester_war_id,
                  status = EXCLUDED.status,
                  data = EXCLUDED.data,
                  updated_at = NOW()
                """,
                (
                    request["request_id"],
                    request.get("target_war_id"),
                    request.get("requester_war_id"),
                    request.get("status"),
                    json.dumps(request),
                ),
            )
        finally:
            cursor.close()
    return request


def delete_request(request_id: str) -> bool:
    if use_json_stores():
        data = _load_all()
        if request_id not in data["requests"]:
            return False
        del data["requests"][request_id]
        _save_all(data)
        return True
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM match_requests WHERE request_id = %s", (request_id,))
            return cursor.rowcount > 0
        finally:
            cursor.close()


def pending_for_target_war(target_war_id: str) -> Optional[Dict[str, Any]]:
    for request in _all_requests().values():
        if request.get("target_war_id") == target_war_id and request.get("status") == "pending":
            return request
    return None


def list_pending_match_for_requester_war(requester_war_id: str) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    if not requester_war_id:
        return out
    for request in _all_requests().values():
        if (
            request.get("status") == "pending"
            and str(request.get("requester_war_id") or "") == str(requester_war_id)
        ):
            out.append(request)
    return out


def create_request(
    board: str,
    target_war_id: str,
    requester_war_id: str,
) -> Dict[str, Any]:
    request = {
        "request_id": str(uuid.uuid4()),
        "board": board,
        "target_war_id": target_war_id,
        "requester_war_id": requester_war_id,
        "status": "pending",
        "notification_channel_id": None,
        "notification_message_id": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    return upsert_request(request)
