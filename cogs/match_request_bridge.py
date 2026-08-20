"""Web → Discord bridge for opponent match challenges created on the companion site."""

from __future__ import annotations

import json
from typing import Any

import interactions
from interactions import ActionRow, Button, ButtonStyle, Extension, IntervalTrigger, Task, listen

from domain.match import get_match_request, upsert_match_request
from utils.billboard_store import find_war
from utils.db import get_conn, use_json_stores
from utils.embeds import build_match_request_embed
from utils.guild_config import get_queue_channel_id


def _match_request_buttons(request_id: str) -> list:
    return [
        ActionRow(
            Button(
                style=ButtonStyle.SUCCESS,
                label="Accept Match",
                custom_id=f"match_accept:{request_id}",
            ),
            Button(
                style=ButtonStyle.DANGER,
                label="Decline",
                custom_id=f"match_deny:{request_id}",
            ),
        )
    ]


class MatchRequestBridge(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot
        self._last_event_id = 0
        self._ready = False

    @listen()
    async def on_startup(self):
        if use_json_stores():
            print("⏭️ MatchRequestBridge skipped (JSON stores / no event_bus)")
            return
        self._last_event_id = self._latest_event_id()
        if not self.poll_match_requests.running:
            self.poll_match_requests.start()
            print("✅ MatchRequestBridge web→Discord task running")
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
                        WHERE id > %s AND event_type = 'match_request'
                        ORDER BY id ASC LIMIT 50
                        """,
                        (self._last_event_id,),
                    )
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
        except Exception as exc:
            print(f"⚠️ MatchRequestBridge event_bus poll failed: {exc}")
            return []

        events = []
        for row_id, _event_type, payload in rows:
            data = payload if isinstance(payload, dict) else json.loads(payload)
            events.append({"id": int(row_id), "payload": data})
        return events

    async def _deliver(self, payload: dict[str, Any]) -> None:
        request_id = payload.get("request_id")
        if not request_id:
            return
        request = get_match_request(str(request_id))
        if not request or request.get("status") != "pending":
            return
        if request.get("notification_message_id"):
            return

        board = request.get("board") or payload.get("board")
        target_war_id = request.get("target_war_id") or payload.get("target_war_id")
        requester_war_id = request.get("requester_war_id") or payload.get("requester_war_id")
        target_war = find_war(board, target_war_id) if board and target_war_id else None
        requester_war = find_war(board, requester_war_id) if board and requester_war_id else None
        if not target_war or not requester_war:
            print(f"⚠️ MatchRequestBridge: war missing for request {request_id}")
            return

        origin_guild = target_war.get("origin_guild_id") or payload.get("origin_guild_id")
        queue_channel_id = get_queue_channel_id(origin_guild) if origin_guild else None
        embed = build_match_request_embed(requester_war)
        buttons = _match_request_buttons(str(request_id))
        mentions = " ".join(
            f"<@{p['discord_id']}>" for p in target_war.get("lineup", []) if p.get("discord_id")
        )

        message = None
        if queue_channel_id:
            try:
                channel = await self.bot.fetch_channel(int(queue_channel_id))
                message = await channel.send(
                    content=mentions or None,
                    embeds=embed,
                    components=buttons,
                )
            except Exception as exc:
                print(f"⚠️ MatchRequestBridge team-queue post failed: {exc}")

        if message is None:
            captain_id = target_war.get("author_discord_id") or payload.get("captain_discord_id")
            if not captain_id:
                print(f"❌ MatchRequestBridge: no captain to DM for {request_id}")
                return
            try:
                user = await self.bot.fetch_user(int(captain_id))
                message = await user.send(embeds=embed, components=buttons)
            except Exception as exc:
                print(f"❌ MatchRequestBridge captain DM failed: {exc}")
                return

        request["notification_channel_id"] = message.channel.id
        request["notification_message_id"] = message.id
        upsert_match_request(request)

    @Task.create(IntervalTrigger(seconds=2))
    async def poll_match_requests(self):
        if use_json_stores() or not self._ready:
            return
        for event in self._poll_events():
            self._last_event_id = event["id"]
            try:
                await self._deliver(event["payload"])
            except Exception as exc:
                print(f"⚠️ MatchRequestBridge handle failed: {exc}")


def setup(bot: interactions.Client):
    MatchRequestBridge(bot)
