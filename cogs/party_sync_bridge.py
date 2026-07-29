"""Web → Discord bridge: refresh/remove hub billboards + team-queue lobby messages."""

from __future__ import annotations

import json
from typing import Any

import interactions
from interactions import Extension, IntervalTrigger, Task, listen

from domain.queue import get_party
from utils.billboard_refresh import refresh_war_billboard_posts, remove_war_from_billboards
from utils.billboard_store import find_post_by_party_id, find_war
from utils.db import get_conn, use_json_stores
from utils.queue_lobby import refresh_queue_lobby_message


class PartySyncBridge(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot
        self._last_event_id = 0
        self._ready = False

    @listen()
    async def on_startup(self):
        if use_json_stores():
            print("⏭️ PartySyncBridge skipped (JSON stores / no event_bus)")
            return
        self._last_event_id = self._latest_event_id()
        if not self.poll_party_sync.running:
            self.poll_party_sync.start()
            print("✅ PartySyncBridge web→Discord task running")
        self._ready = True

    def _latest_event_id(self) -> int:
        try:
            with get_conn() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM event_bus")
                    row = cursor.fetchone()
                finally:
                    cursor.close()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _poll_events(self) -> list[dict[str, Any]]:
        if use_json_stores():
            return []
        try:
            with get_conn() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """
                        SELECT id, event_type, payload FROM event_bus
                        WHERE id > %s AND event_type = 'party_sync'
                        ORDER BY id ASC LIMIT 50
                        """,
                        (self._last_event_id,),
                    )
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
        except Exception as exc:
            print(f"⚠️ PartySyncBridge event_bus poll failed: {exc}")
            return []

        events = []
        for row_id, _event_type, payload in rows:
            data = payload if isinstance(payload, dict) else json.loads(payload)
            events.append({"id": int(row_id), "payload": data})
        return events

    async def _delete_lobby_message(self, payload: dict[str, Any], party: dict | None) -> None:
        channel_id = payload.get("lobby_channel_id") or (party or {}).get("lobby_channel_id")
        message_id = payload.get("lobby_message_id") or (party or {}).get("lobby_message_id")
        if not channel_id or not message_id:
            return
        try:
            channel = await self.bot.fetch_channel(int(channel_id))
            message = await channel.fetch_message(int(message_id))
            await message.delete()
        except Exception as exc:
            print(f"⚠️ PartySyncBridge lobby delete failed: {exc}")

    async def _handle(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action") or "").strip().lower()
        party_id = payload.get("party_id")
        party = get_party(str(party_id)) if party_id else None

        board = payload.get("board")
        war_id = payload.get("war_id")

        if action in ("leave_queue", "cancel"):
            if board and war_id:
                await remove_war_from_billboards(self.bot, str(board), str(war_id))
            if action == "cancel":
                await self._delete_lobby_message(payload, party)
            elif party:
                await refresh_queue_lobby_message(self.bot, party)
            return

        if action in ("roster_update", "post"):
            if not board or not war_id:
                if party_id:
                    found = find_post_by_party_id(str(party_id))
                    if found:
                        board, war = found
                        war_id = war.get("war_id")
            if board and war_id:
                war = find_war(str(board), str(war_id))
                if war:
                    await refresh_war_billboard_posts(self.bot, str(board), war)
                elif action == "roster_update":
                    # Post gone — remove stale Discord messages if any.
                    await remove_war_from_billboards(self.bot, str(board), str(war_id))
            if party:
                await refresh_queue_lobby_message(self.bot, party)
            return

        print(f"⚠️ PartySyncBridge unknown action: {action}")

    @Task.create(IntervalTrigger(seconds=2))
    async def poll_party_sync(self):
        if use_json_stores() or not self._ready:
            return
        for event in self._poll_events():
            self._last_event_id = event["id"]
            try:
                await self._handle(event["payload"])
            except Exception as exc:
                print(f"⚠️ PartySyncBridge handle failed: {exc}")


def setup(bot: interactions.Client):
    PartySyncBridge(bot)
