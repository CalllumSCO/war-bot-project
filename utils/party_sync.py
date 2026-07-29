"""Publish web→Discord party/billboard sync events."""

from __future__ import annotations

from typing import Any, Dict, Optional

from utils.event_bus import publish_event


def publish_party_sync(
    action: str,
    *,
    party: Optional[Dict[str, Any]] = None,
    board: Optional[str] = None,
    war_id: Optional[str] = None,
    party_id: Optional[str] = None,
    lobby_channel_id: Optional[int] = None,
    lobby_message_id: Optional[int] = None,
) -> None:
    """
    Notify the Discord bot to update hub billboards and/or #team-queue.

    Actions:
      - leave_queue: remove hub post; refresh lobby (party still preparing)
      - cancel: remove hub post; delete lobby message
      - roster_update: edit hub post + lobby for current roster
      - post: ensure hub post is visible/up to date
    """
    p = party or {}
    publish_event(
        "party_sync",
        {
            "action": action,
            "party_id": party_id or p.get("party_id"),
            "board": board,
            "war_id": war_id or p.get("match_post_id"),
            "lobby_channel_id": lobby_channel_id
            if lobby_channel_id is not None
            else p.get("lobby_channel_id"),
            "lobby_message_id": lobby_message_id
            if lobby_message_id is not None
            else p.get("lobby_message_id"),
            "guild_id": p.get("guild_id"),
        },
    )
