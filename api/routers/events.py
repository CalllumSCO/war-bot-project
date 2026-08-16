"""
Server-Sent Events stream for the web client.

When Postgres is active, tails the `event_bus` table (populated by
utils.match_message_store for chat, and usable by other stores later).
Always also "bumps" the client whenever the caller's own active party
changes, and sends periodic heartbeats — this covers the JSON-store /
no-`event_bus` fallback case.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api.auth.deps import CurrentUser, get_current_user
from domain.queue import get_active_party_for_user
from utils.db import get_conn, use_json_stores

router = APIRouter(tags=["events"])

POLL_INTERVAL_SECONDS = 2.5
HEARTBEAT_EVERY_N_POLLS = 6  # ~15s at the default poll interval


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _latest_event_id() -> int:
    if use_json_stores():
        return 0
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT COALESCE(MAX(id), 0) FROM event_bus")
                row = cursor.fetchone()
            finally:
                cursor.close()
        return int(row[0]) if row else 0
    except Exception as exc:
        print(f"⚠️ event_bus unavailable, falling back to heartbeat-only SSE: {exc}")
        return 0


def _poll_event_bus(after_id: int) -> list[dict[str, Any]]:
    if use_json_stores():
        return []
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT id, event_type, payload FROM event_bus
                    WHERE id > %s ORDER BY id ASC LIMIT 200
                    """,
                    (after_id,),
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()
    except Exception:
        return []

    events = []
    for row_id, event_type, payload in rows:
        events.append(
            {
                "id": int(row_id),
                "event_type": event_type,
                "payload": payload if isinstance(payload, dict) else json.loads(payload),
            }
        )
    return events


@router.get("/events")
async def stream_events(request: Request, user: CurrentUser = Depends(get_current_user)):
    async def event_generator():
        last_event_id = _latest_event_id()
        last_party_snapshot: str | None = None
        polls_since_heartbeat = 0

        yield _sse("connected", {"discord_id": user.discord_id})

        while True:
            if await request.is_disconnected():
                break

            try:
                for event in _poll_event_bus(last_event_id):
                    last_event_id = event["id"]
                    event_type = str(event["event_type"] or "message")
                    payload = event["payload"]
                    yield _sse(event_type, payload)
                    # Also fan out a generic queue bump so the web board refreshes
                    # even when the client only listens for `queue`.
                    if event_type in ("party_sync", "queue", "hub"):
                        yield _sse("queue", {"source": event_type, "payload": payload})
            except Exception as exc:
                print(f"⚠️ event_bus poll failed: {exc}")

            try:
                party = get_active_party_for_user(user.discord_id)
                snapshot = (party or {}).get("last_updated")
                if snapshot != last_party_snapshot:
                    last_party_snapshot = snapshot
                    yield _sse("party", party)
                    yield _sse("queue", {"source": "party", "party_id": (party or {}).get("party_id")})
            except Exception as exc:
                print(f"⚠️ party bump poll failed: {exc}")

            polls_since_heartbeat += 1
            if polls_since_heartbeat >= HEARTBEAT_EVERY_N_POLLS:
                polls_since_heartbeat = 0
                yield ": heartbeat\n\n"

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
