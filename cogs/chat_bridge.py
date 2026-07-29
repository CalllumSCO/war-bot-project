"""Web → Discord bridge for match/group chat posted from the companion site."""

from __future__ import annotations

import json
from typing import Any

import interactions
from interactions import Extension, Task, IntervalTrigger, listen

from utils.colors import COLORS
from utils.db import get_conn, use_json_stores
from utils.match_session_store import get_session


class ChatBridge(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot
        self._last_event_id = 0
        self._ready = False

    @listen()
    async def on_startup(self):
        if use_json_stores():
            print("⏭️ ChatBridge skipped (JSON stores / no event_bus)")
            return
        self._last_event_id = self._latest_event_id()
        if not self.poll_web_chat.running:
            self.poll_web_chat.start()
            print("✅ ChatBridge web→Discord task running")
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

    def _poll_chat_events(self) -> list[dict[str, Any]]:
        if use_json_stores():
            return []
        try:
            with get_conn() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """
                        SELECT id, event_type, payload FROM event_bus
                        WHERE id > %s AND event_type = 'chat'
                        ORDER BY id ASC LIMIT 100
                        """,
                        (self._last_event_id,),
                    )
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
        except Exception as exc:
            print(f"⚠️ ChatBridge event_bus poll failed: {exc}")
            return []

        events = []
        for row_id, _event_type, payload in rows:
            data = payload if isinstance(payload, dict) else json.loads(payload)
            events.append({"id": int(row_id), "payload": data})
        return events

    async def _post_embed(
        self,
        channel_id: int | None,
        *,
        body: str,
        author_name: str,
        color: int,
        footer: str | None = None,
    ) -> None:
        if not channel_id:
            return
        embed = interactions.Embed(description=body or "*(empty)*", color=color)
        embed.set_footer(text=footer or author_name or "Web")
        try:
            channel = await self.bot.fetch_channel(int(channel_id))
            await channel.send(embeds=embed)
        except Exception as exc:
            print(f"❌ ChatBridge failed to post to {channel_id}: {exc}")

    async def _handle_payload(self, payload: dict[str, Any]) -> None:
        source = (payload.get("source") or "web").lower()
        if source == "discord":
            return

        session_id = payload.get("session_id")
        if not session_id:
            return
        session = get_session(str(session_id))
        if not session:
            return

        channel_kind = payload.get("channel") or "match"
        body = payload.get("body") or ""
        author_name = payload.get("author_name") or "Web"
        author_id = payload.get("author_discord_id")

        if channel_kind == "group":
            color = COLORS["group_chat"]
            # Author's team channel only
            channel_id = None
            if author_id is not None:
                aid = int(author_id)
                if aid in [int(x) for x in session.get("roster_a_ids", [])]:
                    channel_id = session.get("channel_a_id")
                elif aid in [int(x) for x in session.get("roster_b_ids", [])]:
                    channel_id = session.get("channel_b_id")
            footer = (
                f"{author_name} · Team-only — use g: <message> "
                "(or .g <message>) so opponents can't see it"
            )
            await self._post_embed(
                channel_id,
                body=body,
                author_name=author_name,
                color=color,
                footer=footer,
            )
            return

        # Match chat → both team channels
        color = COLORS["match_chat"]
        for channel_id in (session.get("channel_a_id"), session.get("channel_b_id")):
            await self._post_embed(
                channel_id, body=body, author_name=author_name, color=color
            )

    @Task.create(IntervalTrigger(seconds=2))
    async def poll_web_chat(self):
        if use_json_stores() or not self._ready:
            return
        for event in self._poll_chat_events():
            self._last_event_id = event["id"]
            try:
                await self._handle_payload(event["payload"])
            except Exception as exc:
                print(f"⚠️ ChatBridge handle failed: {exc}")


def setup(bot: interactions.Client):
    ChatBridge(bot)
