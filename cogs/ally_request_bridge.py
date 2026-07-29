"""Web → Discord bridge for ally join requests created on the companion site."""

from __future__ import annotations

import json
from typing import Any

import interactions
from interactions import Extension, IntervalTrigger, Task, listen

from domain.match import get_ally_request, upsert_ally_request
from utils.billboard_store import find_war_across_boards
from utils.colors import COLORS
from utils.db import get_conn, use_json_stores
from utils.guild_config import get_queue_channel_id
from interactions import ActionRow, Button, ButtonStyle


def _ally_request_embed(war: dict[str, Any], request: dict[str, Any]) -> interactions.Embed:
    role = request.get("role", "Runner")
    return interactions.Embed(
        title="Ally join request",
        description=(
            f"<@{request['requester_discord_id']}> (**{request.get('requester_name')}**) "
            f"wants to join **{war.get('team_name')}** as **{role}**.\n\n"
            "Any current roster member can **Accept** or **Deny**."
        ),
        color=COLORS["allies"],
    )


def _ally_request_buttons(request_id: str) -> list:
    return [
        ActionRow(
            Button(
                style=ButtonStyle.SUCCESS,
                label="Accept Ally",
                custom_id=f"ally_accept:{request_id}",
            ),
            Button(
                style=ButtonStyle.DANGER,
                label="Deny Ally",
                custom_id=f"ally_deny:{request_id}",
            ),
        )
    ]


class AllyRequestBridge(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot
        self._last_event_id = 0
        self._ready = False

    @listen()
    async def on_startup(self):
        if use_json_stores():
            print("⏭️ AllyRequestBridge skipped (JSON stores / no event_bus)")
            return
        self._last_event_id = self._latest_event_id()
        if not self.poll_ally_requests.running:
            self.poll_ally_requests.start()
            print("✅ AllyRequestBridge web→Discord task running")
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
                        WHERE id > %s AND event_type = 'ally_request'
                        ORDER BY id ASC LIMIT 50
                        """,
                        (self._last_event_id,),
                    )
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
        except Exception as exc:
            print(f"⚠️ AllyRequestBridge event_bus poll failed: {exc}")
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
        request = get_ally_request(str(request_id))
        if not request or request.get("status") != "pending":
            return
        if request.get("notification_message_id"):
            return  # already delivered

        war_id = request.get("war_id") or payload.get("war_id")
        found = find_war_across_boards(war_id) if war_id else None
        if not found:
            print(f"⚠️ AllyRequestBridge: war {war_id} missing for request {request_id}")
            return
        _board, war = found

        origin_guild = war.get("origin_guild_id") or payload.get("origin_guild_id")
        queue_channel_id = get_queue_channel_id(origin_guild) if origin_guild else None

        embed = _ally_request_embed(war, request)
        buttons = _ally_request_buttons(str(request_id))
        roster_mentions = " ".join(
            f"<@{p['discord_id']}>" for p in war.get("lineup", []) if p.get("discord_id")
        )

        message = None
        if queue_channel_id:
            try:
                channel = await self.bot.fetch_channel(int(queue_channel_id))
                message = await channel.send(
                    content=roster_mentions or None,
                    embeds=embed,
                    components=buttons,
                )
            except Exception as exc:
                print(f"⚠️ AllyRequestBridge team-queue post failed: {exc}")

        if message is None:
            captain_id = war.get("author_discord_id") or payload.get("captain_discord_id")
            if not captain_id:
                print(f"❌ AllyRequestBridge: no captain to DM for {request_id}")
                return
            try:
                user = await self.bot.fetch_user(int(captain_id))
                message = await user.send(embeds=embed, components=buttons)
            except Exception as exc:
                print(f"❌ AllyRequestBridge captain DM failed: {exc}")
                return

        request["notification_channel_id"] = message.channel.id
        request["notification_message_id"] = message.id
        upsert_ally_request(request)

    @Task.create(IntervalTrigger(seconds=2))
    async def poll_ally_requests(self):
        if use_json_stores() or not self._ready:
            return
        for event in self._poll_events():
            self._last_event_id = event["id"]
            try:
                await self._deliver(event["payload"])
            except Exception as exc:
                print(f"⚠️ AllyRequestBridge handle failed: {exc}")


def setup(bot: interactions.Client):
    AllyRequestBridge(bot)
