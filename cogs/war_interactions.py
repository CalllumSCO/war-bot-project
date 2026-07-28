import re
from datetime import datetime
from typing import Any, Dict, Optional

import interactions
from interactions import (
    ActionRow,
    Button,
    ButtonStyle,
    ComponentContext,
    Extension,
    component_callback,
)

from classes.player import Player
from utils.ally_request_store import (
    create_ally_request,
    delete_ally_request,
    get_ally_request,
    pending_ally_for_war_and_user,
    upsert_ally_request,
)
from utils.billboard_store import delete_war, find_war_across_boards, find_war_by_author, upsert_war
from utils.billboard_refresh import refresh_war_billboard_posts
from utils.colors import COLORS
from utils.embeds import build_match_request_embed, build_war_embed
from utils.guild_config import get_queue_channel_id
from utils.lineup_lock import find_blocking_lineup, lineup_lock_message
from utils.player_links import require_linked_fc
from utils.match_posting import sync_party_lineup_from_post
from utils.match_request_store import upsert_request
from utils.match_service import start_match_request
from utils.queue_lobby import refresh_queue_lobby_message
from utils.queue_store import get_party, upsert_party
from utils.roster import (
    SEARCH_ALLIES,
    SEARCH_OPPONENTS,
    ally_slots_remaining,
    can_seek_opponents,
    is_roster_full,
    reconcile_search_mode,
)
from utils.search_time import format_search_time, opponent_search_unlocked
from utils.war_buttons import build_war_buttons


def _player_in_lineup(lineup: list, discord_id: int) -> bool:
    return any(entry.get("discord_id") == discord_id for entry in lineup)


def _build_ally_request_embed(war: Dict[str, Any], request: Dict[str, Any]) -> interactions.Embed:
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


def _touch_war(war: Dict[str, Any]) -> Dict[str, Any]:
    war["last_updated"] = datetime.utcnow().isoformat()
    war["ally_count"] = sum(1 for player in war.get("lineup", []) if player.get("ally"))
    return war


def _save_and_refresh(board: str, war: Dict[str, Any]) -> Dict[str, Any]:
    war = _touch_war(war)
    upsert_war(board, war)
    _sync_party_from_war(war)
    return war


def _sync_party_from_war(war: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    party_id = war.get("party_id")
    if not party_id:
        return None
    party = get_party(party_id)
    if not party:
        return None
    party = sync_party_lineup_from_post(party, war)
    upsert_party(party)
    return party


class WarInteractions(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    def _get_war(self, war_id: str) -> Optional[tuple[str, Dict[str, Any]]]:
        return find_war_across_boards(war_id)

    def _is_author(self, war: Dict[str, Any], user_id: int) -> bool:
        return war.get("author_discord_id") == user_id

    async def _refresh_team_lobby_for_war(self, war: Dict[str, Any]) -> None:
        party_id = war.get("party_id")
        if not party_id:
            return
        party = get_party(party_id)
        if party:
            await refresh_queue_lobby_message(self.bot, party)

    async def _refresh_war_on_billboards(
        self,
        board: str,
        war: Dict[str, Any],
        clicked_message=None,
    ) -> None:
        embed = build_war_embed(war)
        components = build_war_buttons(war)

        if clicked_message is not None:
            try:
                await clicked_message.edit(embeds=embed, components=components)
            except Exception as exc:
                print(f"❌ Failed to edit clicked billboard for {war.get('war_id')}: {exc}")

        await refresh_war_billboard_posts(self.bot, board, war)

    @component_callback(re.compile(r"^war_join_ally:(.+)$"))
    async def join_ally_prompt(self, ctx: ComponentContext):
        war_id = ctx.custom_id.split(":", 1)[1]
        found = self._get_war(war_id)
        if not found:
            await ctx.send("This war post no longer exists.", ephemeral=True)
            return

        board, war = found
        if war.get("status") != "open" or war.get("search_mode") != SEARCH_ALLIES:
            await ctx.send("This war is not accepting allies right now.", ephemeral=True)
            return

        if is_roster_full(war.get("lineup", [])):
            await ctx.send("This roster is already full (5/5).", ephemeral=True)
            return

        if not await require_linked_fc(ctx):
            return

        if _player_in_lineup(war.get("lineup", []), ctx.author.id):
            await ctx.send("You are already on this roster.", ephemeral=True)
            return

        block = find_blocking_lineup(ctx.author.id, exclude_war_id=war_id)
        if block:
            await ctx.send(lineup_lock_message(block), ephemeral=True)
            return

        if self._is_author(war, ctx.author.id):
            await ctx.send("You cannot join your own war as an ally.", ephemeral=True)
            return

        rows = [
            ActionRow(
                Button(
                    style=ButtonStyle.PRIMARY,
                    label="Request as Runner",
                    custom_id=f"war_ally_runner:{war_id}",
                ),
                Button(
                    style=ButtonStyle.SUCCESS,
                    label="Request as Bagger",
                    custom_id=f"war_ally_bagger:{war_id}",
                ),
            )
        ]
        await ctx.send(
            f"Choose your role to **request** joining **{war.get('team_name')}** "
            f"({ally_slots_remaining(war.get('lineup', []))} slot(s) left).",
            components=rows,
            ephemeral=True,
        )

    @component_callback(re.compile(r"^war_ally_(runner|bagger):(.+)$"))
    async def join_ally_confirm(self, ctx: ComponentContext):
        match = re.match(r"^war_ally_(runner|bagger):(.+)$", ctx.custom_id)
        role_key = match.group(1)
        war_id = match.group(2)

        found = self._get_war(war_id)
        if not found:
            await ctx.send("This war post no longer exists.", ephemeral=True)
            return

        board, war = found
        lineup = war.get("lineup", [])

        if war.get("status") != "open" or war.get("search_mode") != SEARCH_ALLIES:
            await ctx.send("This war is not accepting allies right now.", ephemeral=True)
            return

        if not await require_linked_fc(ctx):
            return

        if is_roster_full(lineup):
            await ctx.send("This roster is already full (5/5).", ephemeral=True)
            return

        if _player_in_lineup(lineup, ctx.author.id):
            await ctx.send("You are already on this roster.", ephemeral=True)
            return

        if self._is_author(war, ctx.author.id):
            await ctx.send("You cannot join your own war as an ally.", ephemeral=True)
            return

        block = find_blocking_lineup(ctx.author.id, exclude_war_id=war_id)
        if block:
            await ctx.send(lineup_lock_message(block), ephemeral=True)
            return

        if pending_ally_for_war_and_user(war_id, ctx.author.id):
            await ctx.send("You already have a pending ally request for this war.", ephemeral=True)
            return

        is_bagger = role_key == "bagger"
        role_name = "Bagger" if is_bagger else "Runner"
        request = create_ally_request(
            board,
            war_id,
            ctx.author.id,
            ctx.author.display_name,
            role_name,
        )

        queue_channel_id = get_queue_channel_id(war.get("origin_guild_id"))
        if not queue_channel_id:
            delete_ally_request(request["request_id"])
            await ctx.send(
                "That team has no queue channel configured — cannot send the request.",
                ephemeral=True,
            )
            return

        roster_mentions = " ".join(
            f"<@{p['discord_id']}>"
            for p in lineup
            if p.get("discord_id")
        )
        try:
            channel = await self.bot.fetch_channel(queue_channel_id)
            message = await channel.send(
                content=roster_mentions or None,
                embeds=_build_ally_request_embed(war, request),
                components=_ally_request_buttons(request["request_id"]),
            )
        except Exception as exc:
            delete_ally_request(request["request_id"])
            print(f"❌ Failed to post ally request: {exc}")
            await ctx.send("Could not notify the team queue. Try again later.", ephemeral=True)
            return

        request["notification_channel_id"] = message.channel.id
        request["notification_message_id"] = message.id
        upsert_ally_request(request)

        await ctx.send(
            f"Request sent to join **{war.get('team_name')}** as **{role_name}** — "
            "waiting for the team to accept.",
            ephemeral=True,
        )

    @component_callback(re.compile(r"^ally_accept:(.+)$"))
    async def ally_accept(self, ctx: ComponentContext):
        request_id = ctx.custom_id.split(":", 1)[1]
        request = get_ally_request(request_id)
        if not request or request.get("status") != "pending":
            await ctx.send("This ally request is no longer active.", ephemeral=True)
            return

        found = self._get_war(request["war_id"])
        if not found:
            delete_ally_request(request_id)
            await ctx.send("The war post no longer exists.", ephemeral=True)
            return

        board, war = found
        lineup = war.get("lineup", [])

        if not _player_in_lineup(lineup, ctx.author.id):
            await ctx.send("Only current roster members can accept ally requests.", ephemeral=True)
            return

        if war.get("status") != "open" or war.get("search_mode") != SEARCH_ALLIES:
            delete_ally_request(request_id)
            await ctx.send("This war is not accepting allies anymore.", ephemeral=True)
            return

        if is_roster_full(lineup):
            delete_ally_request(request_id)
            await ctx.send("Roster is already full (5/5).", ephemeral=True)
            return

        requester_id = request["requester_discord_id"]
        if _player_in_lineup(lineup, requester_id):
            delete_ally_request(request_id)
            await ctx.send("That player is already on the roster.", ephemeral=True)
            return

        block = find_blocking_lineup(requester_id, exclude_war_id=war["war_id"])
        if block:
            await ctx.send(
                f"Cannot accept — {lineup_lock_message(block)}",
                ephemeral=True,
            )
            return

        role_name = request.get("role", "Runner")
        is_bagger = role_name == "Bagger"
        lineup.append(
            Player(
                player=request.get("requester_name") or str(requester_id),
                role=role_name,
                ally=True,
                bagger=is_bagger,
                discord_id=requester_id,
            ).to_dict()
        )
        war["lineup"] = lineup
        war["search_mode"] = reconcile_search_mode(
            war.get("search_mode", SEARCH_ALLIES),
            lineup,
            search_time=war.get("start_time", "ASAP"),
            created_at=war.get("created_at") or war.get("last_updated"),
        )
        war = _save_and_refresh(board, war)

        request["status"] = "accepted"
        upsert_ally_request(request)
        delete_ally_request(request_id)

        try:
            await ctx.message.edit(
                content=f"Accepted <@{requester_id}> as **{role_name}** ally.",
                embeds=[],
                components=[],
            )
        except Exception:
            pass

        await self._refresh_war_on_billboards(board, war)
        await self._refresh_team_lobby_for_war(war)

        try:
            user = await self.bot.fetch_user(requester_id)
            await user.send(
                f"Your ally request for **{war.get('team_name')}** as **{role_name}** was **accepted**."
            )
        except Exception:
            pass

        await ctx.send(
            f"Accepted <@{requester_id}> as **{role_name}**.",
            ephemeral=True,
        )

    @component_callback(re.compile(r"^ally_deny:(.+)$"))
    async def ally_deny(self, ctx: ComponentContext):
        request_id = ctx.custom_id.split(":", 1)[1]
        request = get_ally_request(request_id)
        if not request or request.get("status") != "pending":
            await ctx.send("This ally request is no longer active.", ephemeral=True)
            return

        found = self._get_war(request["war_id"])
        if not found:
            delete_ally_request(request_id)
            await ctx.send("The war post no longer exists.", ephemeral=True)
            return

        _, war = found
        if not _player_in_lineup(war.get("lineup", []), ctx.author.id):
            await ctx.send("Only current roster members can deny ally requests.", ephemeral=True)
            return

        requester_id = request["requester_discord_id"]
        delete_ally_request(request_id)

        try:
            await ctx.message.edit(
                content=f"Denied ally request from <@{requester_id}>.",
                embeds=[],
                components=[],
            )
        except Exception:
            pass

        try:
            user = await self.bot.fetch_user(requester_id)
            await user.send(
                f"Your ally request for **{war.get('team_name')}** was **denied**."
            )
        except Exception:
            pass

        await ctx.send("Ally request denied.", ephemeral=True)

    @component_callback(re.compile(r"^war_seek_opponents:(.+)$"))
    async def seek_opponents(self, ctx: ComponentContext):
        war_id = ctx.custom_id.split(":", 1)[1]
        found = self._get_war(war_id)
        if not found:
            await ctx.send("This war post no longer exists.", ephemeral=True)
            return

        board, war = found
        if not self._is_author(war, ctx.author.id):
            await ctx.send("Only the war author can switch to opponent search.", ephemeral=True)
            return

        if not can_seek_opponents(war.get("lineup", [])):
            await ctx.send(
                "You need a full **5/5** lineup with a bagger before looking for opponents.",
                ephemeral=True,
            )
            return

        if not opponent_search_unlocked(
            war.get("start_time", "ASAP"),
            created_at=war.get("created_at") or war.get("last_updated"),
        ):
            await ctx.send(
                f"Opponent search opens at **{format_search_time(war.get('start_time'))}**.",
                ephemeral=True,
            )
            return

        war["search_mode"] = SEARCH_OPPONENTS
        war = _save_and_refresh(board, war)
        await ctx.send("Now **looking for opponents**.", ephemeral=True)
        await self._refresh_war_on_billboards(board, war, ctx.message)

    @component_callback(re.compile(r"^war_seek_allies:(.+)$"))
    async def seek_allies(self, ctx: ComponentContext):
        war_id = ctx.custom_id.split(":", 1)[1]
        found = self._get_war(war_id)
        if not found:
            await ctx.send("This war post no longer exists.", ephemeral=True)
            return

        board, war = found
        if not self._is_author(war, ctx.author.id):
            await ctx.send("Only the war author can switch back to ally search.", ephemeral=True)
            return

        war["search_mode"] = SEARCH_ALLIES
        war = _save_and_refresh(board, war)
        await ctx.send("Now **looking for allies**.", ephemeral=True)
        await self._refresh_war_on_billboards(board, war, ctx.message)

    @component_callback(re.compile(r"^war_request:(.+)$"))
    async def request_match(self, ctx: ComponentContext):
        war_id = ctx.custom_id.split(":", 1)[1]
        found = self._get_war(war_id)
        if not found:
            await ctx.send("This war post no longer exists.", ephemeral=True)
            return

        board, target_war = found

        if target_war.get("status") != "open":
            await ctx.send("This war is no longer available.", ephemeral=True)
            return

        if target_war.get("search_mode") != SEARCH_OPPONENTS:
            await ctx.send("This team is still looking for allies, not opponents.", ephemeral=True)
            return

        if not can_seek_opponents(target_war.get("lineup", [])):
            await ctx.send("This team does not have a confirmed 5/5 lineup yet.", ephemeral=True)
            return

        if self._is_author(target_war, ctx.author.id):
            await ctx.send("You cannot request your own war.", ephemeral=True)
            return

        requester_war = find_war_by_author(board, ctx.author.id)
        if not requester_war:
            await ctx.send(
                "You need your own open war post in **Looking For Opponents** mode before requesting.",
                ephemeral=True,
            )
            return

        if requester_war.get("search_mode") != SEARCH_OPPONENTS:
            await ctx.send("Switch your war to **Looking For Opponents** first.", ephemeral=True)
            return

        if not can_seek_opponents(requester_war.get("lineup", [])):
            await ctx.send("Your roster must be **5/5** with at least **1 bagger** to request.", ephemeral=True)
            return

        request, error = start_match_request(board, target_war["war_id"], requester_war["war_id"])
        if error:
            await ctx.send(error, ephemeral=True)
            return

        queue_channel_id = get_queue_channel_id(target_war["origin_guild_id"])
        if not queue_channel_id:
            await ctx.send("Could not notify the other team — they have no queue channel configured.", ephemeral=True)
            return

        channel = await self.bot.fetch_channel(queue_channel_id)
        components = [
            ActionRow(
                Button(
                    style=ButtonStyle.SUCCESS,
                    label="Accept Match",
                    custom_id=f"match_accept:{request['request_id']}",
                ),
                Button(
                    style=ButtonStyle.DANGER,
                    label="Decline",
                    custom_id=f"match_deny:{request['request_id']}",
                ),
            )
        ]
        msg = await channel.send(
            content=f"<@{target_war['author_discord_id']}> — **{requester_war.get('team_name')}** requested a match!",
            embeds=build_match_request_embed(requester_war),
            components=components,
        )
        request["notification_channel_id"] = channel.id
        request["notification_message_id"] = msg.id
        upsert_request(request)

        await ctx.send(
            f"Match request sent to **{target_war.get('team_name')}**. Waiting for their captain to accept.",
            ephemeral=True,
        )

    @component_callback(re.compile(r"^war_cancel:(.+)$"))
    async def cancel_war(self, ctx: ComponentContext):
        war_id = ctx.custom_id.split(":", 1)[1]
        found = self._get_war(war_id)
        if not found:
            await ctx.send("This war post no longer exists.", ephemeral=True)
            return

        board, war = found
        if not self._is_author(war, ctx.author.id):
            await ctx.send("Only the war author can cancel this post.", ephemeral=True)
            return

        if war.get("status") == "matched":
            opponent = war.get("matched_opponent") or {}
            opponent_id = opponent.get("war_id")
            if opponent_id:
                opponent_found = self._get_war(opponent_id)
                if opponent_found:
                    opp_board, opp_war = opponent_found
                    opp_war["status"] = "open"
                    opp_war["matched_opponent"] = None
                    _save_and_refresh(opp_board, opp_war)

        war["status"] = "cancelled"
        war["matched_opponent"] = None
        _save_and_refresh(board, war)
        delete_war(board, war_id)
        party_id = war.get("party_id")
        if party_id:
            from utils.queue_store import delete_party
            delete_party(party_id)

        try:
            await ctx.message.delete()
        except Exception:
            pass

        await ctx.send("War post cancelled.", ephemeral=True)

    @component_callback(re.compile(r"^war_delete:(.+)$"))
    async def delete_war_post(self, ctx: ComponentContext):
        war_id = ctx.custom_id.split(":", 1)[1]
        found = self._get_war(war_id)
        if not found:
            await ctx.send("This war post no longer exists.", ephemeral=True)
            return

        board, war = found
        if not self._is_author(war, ctx.author.id):
            await ctx.send("Only the war author can delete this post.", ephemeral=True)
            return

        if war.get("status") == "matched":
            opponent = war.get("matched_opponent") or {}
            opponent_id = opponent.get("war_id")
            if opponent_id:
                opponent_found = self._get_war(opponent_id)
                if opponent_found:
                    opp_board, opp_war = opponent_found
                    opp_war["status"] = "open"
                    opp_war["matched_opponent"] = None
                    _save_and_refresh(opp_board, opp_war)

        delete_war(board, war_id)
        party_id = war.get("party_id")
        if party_id:
            from utils.queue_store import delete_party
            delete_party(party_id)

        try:
            await ctx.message.delete()
        except Exception:
            pass

        await ctx.send("War post deleted.", ephemeral=True)


def setup(bot: interactions.Client):
    WarInteractions(bot)
