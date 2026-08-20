import re

import interactions
from interactions import ComponentContext, Extension, component_callback

from classes.player import Player
from domain.match import board_for_party
from domain.queue import (
    cancel_party,
    finalize_roster_change,
    get_party,
    post_party_to_billboard,
    sync_billboard_post_from_party,
    touch_roster_change,
    upsert_party,
)
from domain.roster import PARTY_PREPARING, is_roster_full, team_queue_lobby_active
from utils.billboard_refresh import refresh_war_billboard_posts
from utils.lineup_lock import find_blocking_lineup, lineup_lock_message
from utils.player_links import require_linked_fc
from utils.queue_lobby import refresh_queue_lobby_message
from utils.roster import role_allowed_for_lineup


def _player_in_lineup(lineup: list, discord_id: int) -> bool:
    return any(entry.get("discord_id") == discord_id for entry in lineup)


async def _defer_ephemeral(ctx: ComponentContext) -> None:
    """Ack within Discord's 3s window before slow Lounge / message edits."""
    from utils.discord_defer import defer_ephemeral

    await defer_ephemeral(ctx)


class QueueInteractions(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    async def _refresh_lobby(self, party: dict) -> None:
        await refresh_queue_lobby_message(self.bot, party)

    @component_callback(re.compile(r"^queue_join_(runner|bagger):(.+)$"))
    async def queue_join(self, ctx: ComponentContext):
        match = re.match(r"^queue_join_(runner|bagger):(.+)$", ctx.custom_id)
        role_key = match.group(1)
        party_id = match.group(2)

        party = get_party(party_id)
        if not party or not team_queue_lobby_active(party):
            await ctx.send("This queue lobby is no longer open.", ephemeral=True)
            return

        if ctx.guild_id != party.get("guild_id"):
            await ctx.send("Only members of **this team's server** can join the queue lobby.", ephemeral=True)
            return

        lineup = party.get("lineup", [])
        if is_roster_full(lineup):
            await ctx.send("This queue is already full (5/5).", ephemeral=True)
            return

        if _player_in_lineup(lineup, ctx.author.id):
            await ctx.send("You are already in this queue.", ephemeral=True)
            return

        is_bagger = role_key == "bagger"
        if not role_allowed_for_lineup(lineup, bagger=is_bagger):
            await ctx.send(
                "That role isn't available for this lobby right now "
                "(4 runners → bagger only; bagger already in → runner only).",
                ephemeral=True,
            )
            return

        block = find_blocking_lineup(ctx.author.id, exclude_party_id=party_id)
        if block:
            await ctx.send(lineup_lock_message(block), ephemeral=True)
            return

        # Lounge FC check + lobby edit can exceed 3s — defer first so the
        # "please /profile link" ephemeral still lands if they're unlinked.
        await _defer_ephemeral(ctx)

        if not await require_linked_fc(ctx, party.get("guild_id")):
            return

        role_name = "Bagger" if is_bagger else "Runner"
        lineup.append(
            Player(
                player=ctx.author.display_name,
                role=role_name,
                ally=False,
                bagger=is_bagger,
                discord_id=ctx.author.id,
            ).to_dict()
        )
        party["lineup"] = lineup
        was_hidden = bool(party.get("queue_hidden"))
        party = touch_roster_change(party)
        upsert_party(party)
        party = finalize_roster_change(party, was_hidden=was_hidden)

        from utils.pending_outbound import (
            clear_outbound_pending_for_party,
            clear_outbound_pending_for_user,
        )

        clear_outbound_pending_for_party(party_id)
        clear_outbound_pending_for_user(int(ctx.author.id))

        if party.get("status") != PARTY_PREPARING:
            synced = sync_billboard_post_from_party(party)
            if synced:
                board, war = synced
                upsert_party(party)
                await refresh_war_billboard_posts(self.bot, board, war)
        await self._refresh_lobby(party)
        await ctx.send(f"You joined the queue as **{role_name}**.", ephemeral=True)

    @component_callback(re.compile(r"^queue_leave:(.+)$"))
    async def queue_leave(self, ctx: ComponentContext):
        party_id = ctx.custom_id.split(":", 1)[1]
        party = get_party(party_id)
        if not party or not team_queue_lobby_active(party):
            await ctx.send("This queue lobby is no longer open.", ephemeral=True)
            return

        if party.get("captain_discord_id") == ctx.author.id:
            await ctx.send("Captains must use **Cancel Queue** instead of leave.", ephemeral=True)
            return

        lineup = [p for p in party.get("lineup", []) if p.get("discord_id") != ctx.author.id]
        if len(lineup) == len(party.get("lineup", [])):
            await ctx.send("You are not in this queue.", ephemeral=True)
            return

        await _defer_ephemeral(ctx)

        party["lineup"] = lineup
        was_hidden = bool(party.get("queue_hidden"))
        party = touch_roster_change(party)
        upsert_party(party)
        party = finalize_roster_change(party, was_hidden=was_hidden)
        if party.get("status") != PARTY_PREPARING:
            synced = sync_billboard_post_from_party(party)
            if synced:
                board, war = synced
                upsert_party(party)
                await refresh_war_billboard_posts(self.bot, board, war)
        await self._refresh_lobby(party)
        await ctx.send("You left the queue.", ephemeral=True)

    @component_callback(re.compile(r"^queue_post:(.+)$"))
    async def queue_post(self, ctx: ComponentContext):
        party_id = ctx.custom_id.split(":", 1)[1]
        party = get_party(party_id)
        if not party or party.get("status") != PARTY_PREPARING:
            await ctx.send("This queue is not ready to post.", ephemeral=True)
            return

        if ctx.author.id != party.get("captain_discord_id"):
            await ctx.send("Only the captain can post.", ephemeral=True)
            return

        await _defer_ephemeral(ctx)

        post, message = post_party_to_billboard(party)
        if not post:
            await ctx.send(message, ephemeral=True)
            return

        party = get_party(party_id)
        await refresh_war_billboard_posts(self.bot, board_for_party(party), post)
        await self._refresh_lobby(party)
        await ctx.send(message, ephemeral=True)

    @component_callback(re.compile(r"^queue_cancel:(.+)$"))
    async def queue_cancel(self, ctx: ComponentContext):
        party_id = ctx.custom_id.split(":", 1)[1]
        party = get_party(party_id)
        if not party:
            await ctx.send("Queue not found.", ephemeral=True)
            return

        if ctx.author.id != party.get("captain_discord_id"):
            await ctx.send("Only the captain can cancel the queue.", ephemeral=True)
            return

        await _defer_ephemeral(ctx)

        cancel_party(party_id)
        try:
            if ctx.message:
                await ctx.message.delete()
        except Exception:
            pass
        await ctx.send("Queue cancelled.", ephemeral=True)


def setup(bot: interactions.Client):
    QueueInteractions(bot)
