"""Match chat messages — Postgres match_messages or temp JSON fallback."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

STORE_PATH = os.path.join(DATA_DIR, "match-messages.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(STORE_PATH):
        return {"messages": []}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "messages" in data else {"messages": []}
    except json.JSONDecodeError:
        return {"messages": []}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def append_message(
    session_id: str,
    channel: str,
    body: str,
    *,
    author_discord_id: Optional[int] = None,
    author_name: Optional[str] = None,
    source: str = "web",
) -> Dict[str, Any]:
    channel = "group" if channel == "group" else "match"
    msg = {
        "session_id": session_id,
        "channel": channel,
        "body": body,
        "author_discord_id": author_discord_id,
        "author_name": author_name,
        "source": source or "web",
        "created_at": datetime.utcnow().isoformat(),
    }
    if use_json_stores():
        data = _load_all()
        msg["id"] = len(data["messages"]) + 1
        data["messages"].append(msg)
        _save_all(data)
        _publish_event("chat", msg)
        return msg

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO match_messages (
                  session_id, channel, author_discord_id, author_name, body, created_at
                ) VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id, created_at
                """,
                (
                    session_id,
                    channel,
                    author_discord_id,
                    author_name,
                    body,
                ),
            )
            row = cursor.fetchone()
            msg["id"] = int(row[0])
            msg["created_at"] = row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
        finally:
            cursor.close()
    _publish_event("chat", msg)
    return msg


def list_messages(
    session_id: str,
    channel: str,
    *,
    limit: int = 50,
    before_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    channel = "group" if channel == "group" else "match"
    if use_json_stores():
        rows = [
            m
            for m in _load_all()["messages"]
            if m.get("session_id") == session_id and m.get("channel") == channel
        ]
        rows.sort(key=lambda m: m.get("id") or 0)
        if before_id:
            rows = [m for m in rows if int(m.get("id") or 0) < before_id]
        return rows[-limit:]

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            if before_id:
                cursor.execute(
                    """
                    SELECT id, session_id, channel, author_discord_id, author_name, body, created_at
                    FROM match_messages
                    WHERE session_id = %s AND channel = %s AND id < %s
                    ORDER BY id DESC LIMIT %s
                    """,
                    (session_id, channel, before_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, session_id, channel, author_discord_id, author_name, body, created_at
                    FROM match_messages
                    WHERE session_id = %s AND channel = %s
                    ORDER BY id DESC LIMIT %s
                    """,
                    (session_id, channel, limit),
                )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    out = []
    for row in reversed(rows):
        out.append(
            {
                "id": int(row[0]),
                "session_id": row[1],
                "channel": row[2],
                "author_discord_id": row[3],
                "author_name": row[4],
                "body": row[5],
                "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
            }
        )
    return out


def _publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    from utils.event_bus import publish_event

    publish_event(event_type, payload)