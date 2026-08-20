import asyncio
import re

import interactions
from interactions import ComponentContext, Extension, component_callback

from domain.match import (
    delete_match_request,
    finalize_match,
    get_match_request,
    upsert_match_request,
)
from domain.queue import get_party
from utils.billboard_store import find_war
from utils.billboard_refresh import refresh_war_billboard_posts
from utils.discord_defer import defer_ephemeral, send_ephemeral
from utils.guild_config import get_queue_channel_id
from utils.match_service import create_war_comm_channels, reopen_wars_after_failed_accept
from utils.queue_lobby import refresh_queue_lobby_message


class MatchInteractions(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    async def _disable_notification(self, request: dict, note: str) -> None:
        channel_id = request.get("notification_channel_id")
        message_id = request.get("notification_message_id")
        if not channel_id or not message_id:
            return
        try:
            channel = await self.bot.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
            embed = message.embeds[0] if message.embeds else interactions.Embed(title="Match request")
            embed.description = f"{embed.description or ''}\n\n**{note}**"
            await message.edit(embeds=embed, components=[])
        except Exception:
            pass

    async def _refresh_billboards_later(self, board: str, *wars: dict) -> None:
        for war in wars:
            try:
                await refresh_war_billboard_posts(self.bot, board, war)
            except Exception as exc:
                print(f"⚠️ match accept billboard refresh failed: {exc}")

    @component_callback(re.compile(r"^match_accept:(.+)$"))
    async def match_accept(self, ctx: ComponentContext):
        if not await defer_ephemeral(ctx):
            return
        request_id = ctx.custom_id.split(":", 1)[1]
        request = get_match_request(request_id)
        if not request or request.get("status") != "pending":
            await send_ephemeral(ctx, "This match request is no longer active.")
            return

        board = request["board"]
        target_war = find_war(board, request["target_war_id"])
        requester_war = find_war(board, request["requester_war_id"])
        if not target_war or not requester_war:
            await send_ephemeral(ctx, "One of the war posts no longer exists.")
            delete_match_request(request_id)
            return

        if ctx.author.id != int(target_war.get("author_discord_id") or 0):
            await send_ephemeral(ctx, "Only the defending team's **captain** can accept this match.")
            return

        try:
            session = await create_war_comm_channels(self.bot, board, target_war, requester_war)
            if not session:
                await send_ephemeral(
                    ctx,
                    "Couldn't create war comm channels. Check bot permissions (Manage Channels) and try again.",
                )
                return

            target_war, requester_war = finalize_match(board, target_war, requester_war)

            request["status"] = "accepted"
            upsert_match_request(request)
            delete_match_request(request_id)

            asyncio.create_task(self._refresh_billboards_later(board, target_war, requester_war))
            asyncio.create_task(self._disable_notification(request, f"Accepted by {ctx.author.display_name}."))

            for war in (target_war, requester_war):
                party_id = war.get("party_id")
                if party_id:
                    party = get_party(party_id)
                    if party:
                        asyncio.create_task(refresh_queue_lobby_message(self.bot, party))

            requester_channel = get_queue_channel_id(requester_war.get("origin_guild_id"))
            if requester_channel:
                try:
                    ch = await self.bot.fetch_channel(requester_channel)
                    if session.get("channel_b_id"):
                        channel_note = f"Use <#{session['channel_b_id']}> to coordinate."
                    else:
                        channel_note = "Coordinate on the companion site match page."
                    await ch.send(
                        f"<@{requester_war['author_discord_id']}> — **{target_war.get('team_name')}** accepted your match! "
                        f"{channel_note}"
                    )
                except Exception:
                    pass

            from utils.event_bus import publish_event

            publish_event(
                "match_confirmed",
                {
                    "session_id": session.get("session_id"),
                    "board": board,
                    "requester_war_id": requester_war.get("war_id"),
                    "target_war_id": target_war.get("war_id"),
                },
            )

            target_channel_note = (
                f"Your team channel: <#{session['channel_a_id']}>"
                if session.get("channel_a_id")
                else "Coordinate on the companion site match page."
            )
            await send_ephemeral(
                ctx,
                f"Match confirmed vs **{requester_war.get('team_name')}**! {target_channel_note}",
            )
        except Exception as exc:
            print(f"❌ match_accept failed for {request_id}: {exc}")
            try:
                reopen_wars_after_failed_accept(board, target_war, requester_war)
            except Exception as rollback_exc:
                print(f"⚠️ match_accept rollback failed: {rollback_exc}")
            await send_ephemeral(ctx, "Accept failed — your team is still in queue. Try again in a moment.")

    @component_callback(re.compile(r"^match_deny:(.+)$"))
    async def match_deny(self, ctx: ComponentContext):
        if not await defer_ephemeral(ctx):
            return
        request_id = ctx.custom_id.split(":", 1)[1]
        request = get_match_request(request_id)
        if not request or request.get("status") != "pending":
            await send_ephemeral(ctx, "This match request is no longer active.")
            return

        board = request["board"]
        target_war = find_war(board, request["target_war_id"])
        requester_war = find_war(board, request["requester_war_id"])
        if not target_war:
            await send_ephemeral(ctx, "War post not found.")
            delete_match_request(request_id)
            return

        if ctx.author.id != int(target_war.get("author_discord_id") or 0):
            await send_ephemeral(ctx, "Only the defending team's **captain** can decline.")
            return

        request["status"] = "denied"
        upsert_match_request(request)
        delete_match_request(request_id)
        await self._disable_notification(request, f"Declined by {ctx.author.display_name}.")

        if requester_war:
            requester_channel = get_queue_channel_id(requester_war.get("origin_guild_id"))
            if requester_channel:
                try:
                    ch = await self.bot.fetch_channel(requester_channel)
                    await ch.send(
                        f"<@{requester_war['author_discord_id']}> — **{target_war.get('team_name')}** declined your match request."
                    )
                except Exception:
                    pass

        await send_ephemeral(ctx, "Match request declined.")


def setup(bot: interactions.Client):
    MatchInteractions(bot)
