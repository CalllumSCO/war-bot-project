import re
from typing import Optional

import interactions
from interactions import (
    ActionRow,
    Extension,
    SlashContext,
    StringSelectMenu,
    StringSelectOption,
    ComponentContext,
    slash_command,
    slash_option,
    OptionType,
    SlashCommandChoice,
    component_callback,
)

from classes.player import Player
from classes.queue_party import MODE_CASUAL, MODE_RANKED, PARTY_PREPARING, QueueParty
from utils.billboard_store import find_post_by_party_id
from utils.billboard_refresh import refresh_war_billboard_posts
from utils.config import SCOPES
from utils.embeds import build_queue_party_embed, build_queue_status_embed
from utils.guild_config import get_queue_channel_id
from utils.lineup_lock import find_blocking_lineup, lineup_lock_message
from utils.match_service import board_for_party
from utils.modal_labels import (
    build_label_modal,
    label_string_select,
    patch_modal_context,
    select_option,
)
from utils.queue_lobby import refresh_queue_lobby_message
from utils.queue_service import cancel_party, post_party_to_billboard
from utils.queue_buttons import build_queue_party_buttons
from utils.queue_store import (
    get_active_party_for_guild,
    get_active_party_for_user,
    get_party,
    upsert_party,
)
from utils.search_time import format_search_time, parse_search_time
from utils.team_store import get_team_by_guild

patch_modal_context()


def _parse_start_modal(kwargs: dict) -> tuple[Optional[dict], Optional[str]]:
    track = (kwargs.get("track") or "RT").strip().upper()
    if track not in ("RT", "CT"):
        return None, "Track must be **RT** or **CT**."

    bagger_raw = (kwargs.get("bagger") or "no").strip().lower()
    if bagger_raw in ("yes", "y", "true", "bagger", "bag", "b", "1"):
        is_bagger = True
    elif bagger_raw in ("no", "n", "false", "runner", "run", "r", "0"):
        is_bagger = False
    else:
        return None, "Bagger must be **yes** or **no**."

    mode_raw = (kwargs.get("mode") or "ranked").strip().lower()
    if mode_raw in ("casual", "c"):
        mode = MODE_CASUAL
    elif mode_raw in ("ranked", "rank", "r", ""):
        mode = MODE_RANKED
    else:
        return None, "Mode must be **ranked** or **casual**."

    return {
        "track": track,
        "is_bagger": is_bagger,
        "mode": mode,
    }, None


def _casual_time_select(track: str, is_bagger: bool) -> StringSelectMenu:
    options = [
        StringSelectOption(
            label="Right away",
            value="ASAP",
        )
    ]
    for hour in range(24):
        options.append(
            StringSelectOption(
                label=f"{hour:02d}:00",
                value=f"{hour:02d}",
            )
        )
    bagger_flag = "1" if is_bagger else "0"
    return StringSelectMenu(
        *options,
        custom_id=f"queue_casual_time:{track}:{bagger_flag}",
        placeholder="When should opponent search start?",
        min_values=1,
        max_values=1,
    )


class QueueCommands(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    async def _refresh_lobby_message(self, party: dict) -> None:
        await refresh_queue_lobby_message(self.bot, party)

    def _require_team_server(self, ctx) -> tuple[dict, str] | tuple[None, None]:
        if not ctx.guild:
            return None, "Use this in your team's Discord server."
        team = get_team_by_guild(ctx.guild.id)
        if not team:
            return None, "Register this server with `/team` first."
        return team, ""

    async def _create_queue_lobby(
        self,
        *,
        bot,
        guild,
        author,
        team: dict,
        track: str,
        is_bagger: bool,
        mode: str,
        search_time: str,
        reply_ctx,
    ) -> None:
        if get_active_party_for_guild(guild.id):
            await reply_ctx.send(
                "This server already has an active queue. Use `/queue status`.",
                ephemeral=True,
            )
            return

        if get_active_party_for_user(author.id):
            await reply_ctx.send("You are already in a queue party.", ephemeral=True)
            return

        block = find_blocking_lineup(author.id)
        if block:
            await reply_ctx.send(lineup_lock_message(block), ephemeral=True)
            return

        queue_channel_id = get_queue_channel_id(guild.id) or getattr(
            reply_ctx, "channel_id", None
        )
        captain = Player(
            player=author.display_name,
            role="Bagger" if is_bagger else "Runner",
            ally=False,
            bagger=is_bagger,
            discord_id=author.id,
        )

        party = QueueParty(
            team_id=team["team_id"],
            guild_id=guild.id,
            team_name=team["name"],
            war_type=track,
            captain_discord_id=author.id,
            search_time=search_time,
            mode=mode,
            status=PARTY_PREPARING,
            lineup=[captain],
            lobby_channel_id=queue_channel_id,
        )
        party_dict = party.to_dict()

        channel = await bot.fetch_channel(queue_channel_id)
        message = await channel.send(
            embeds=build_queue_party_embed(party_dict),
            components=build_queue_party_buttons(party_dict),
        )
        party_dict["lobby_message_id"] = message.id
        upsert_party(party_dict)

        time_note = format_search_time(search_time) if mode == MODE_CASUAL else "Right away"
        await reply_ctx.send(
            f"Lobby ready in <#{queue_channel_id}>.\n"
            f"**{track}** · **{mode.title()}** · **{time_note}**\n"
            "Teammates can join from the lobby buttons.",
            ephemeral=True,
        )

    @slash_command(
        name="queue",
        description="Team queue",
        sub_cmd_name="start",
        sub_cmd_description="Captain starts a lobby in #team-queue.",
        scopes=SCOPES,
    )
    async def queue_start(self, ctx: SlashContext):
        team, error = self._require_team_server(ctx)
        if error:
            await ctx.send(error, ephemeral=True)
            return

        if get_active_party_for_guild(ctx.guild.id):
            await ctx.send("This server already has an active queue. Use `/queue status`.", ephemeral=True)
            return

        block = find_blocking_lineup(ctx.author.id)
        if block:
            await ctx.send(lineup_lock_message(block), ephemeral=True)
            return

        modal_payload, modal_handle = build_label_modal(
            title="Start queue",
            labels=[
                label_string_select(
                    label="Track",
                    custom_id="track",
                    placeholder="Choose a track",
                    options=[
                        select_option("RT", "RT"),
                        select_option("CT", "CT"),
                    ],
                ),
                label_string_select(
                    label="Mode",
                    custom_id="mode",
                    placeholder="Ranked or casual?",
                    options=[
                        select_option("Ranked", "ranked"),
                        select_option("Casual", "casual"),
                    ],
                ),
                label_string_select(
                    label="Your role",
                    custom_id="bagger",
                    placeholder="Runner or bagger?",
                    options=[
                        select_option("Runner", "no"),
                        select_option("Bagger", "yes"),
                    ],
                ),
            ],
        )
        await ctx.send_modal(modal_payload)
        m_ctx = await self.bot.wait_for_modal(modal_handle, ctx.author)

        parsed, parse_error = _parse_start_modal(m_ctx.kwargs)
        if parse_error:
            await m_ctx.send(parse_error, ephemeral=True)
            return

        if parsed["mode"] == MODE_RANKED:
            await self._create_queue_lobby(
                bot=self.bot,
                guild=ctx.guild,
                author=ctx.author,
                team=team,
                track=parsed["track"],
                is_bagger=parsed["is_bagger"],
                mode=MODE_RANKED,
                search_time="ASAP",
                reply_ctx=m_ctx,
            )
            return

        select = _casual_time_select(parsed["track"], parsed["is_bagger"])
        await m_ctx.send(
            "When should you start looking for opponents?",
            components=[ActionRow(select)],
            ephemeral=True,
        )

    @component_callback(re.compile(r"^queue_casual_time:(RT|CT):([01])$"))
    async def queue_casual_time_picked(self, ctx: ComponentContext):
        match = re.match(r"^queue_casual_time:(RT|CT):([01])$", ctx.custom_id)
        if not match:
            await ctx.send("Invalid time selection.", ephemeral=True)
            return

        track = match.group(1)
        is_bagger = match.group(2) == "1"
        values = ctx.values or []
        if not values:
            await ctx.send("Pick a search time.", ephemeral=True)
            return

        search_time, time_error = parse_search_time(values[0])
        if time_error:
            await ctx.send(time_error, ephemeral=True)
            return

        team, error = self._require_team_server(ctx)
        if error:
            await ctx.send(error, ephemeral=True)
            return

        await self._create_queue_lobby(
            bot=self.bot,
            guild=ctx.guild,
            author=ctx.author,
            team=team,
            track=track,
            is_bagger=is_bagger,
            mode=MODE_CASUAL,
            search_time=search_time or "ASAP",
            reply_ctx=ctx,
        )

        try:
            await ctx.edit_origin(
                content=f"Casual lobby started · **{track}** · **{format_search_time(search_time)}**",
                components=[],
            )
        except Exception:
            pass

    @slash_command(
        name="queue",
        description="Team queue",
        sub_cmd_name="post",
        sub_cmd_description="Post your lobby to the hub.",
        scopes=SCOPES,
    )
    @slash_option(
        name="looking_for",
        description="Looking for allies or opponents?",
        required=False,
        opt_type=OptionType.STRING,
        choices=[
            SlashCommandChoice(name="Allies", value="allies"),
            SlashCommandChoice(name="Opponents", value="opponents"),
        ],
    )
    async def queue_post(self, ctx: SlashContext, looking_for: Optional[str] = None):
        _, error = self._require_team_server(ctx)
        if error:
            await ctx.send(error, ephemeral=True)
            return

        party = get_active_party_for_user(ctx.author.id)
        if not party or party.get("status") != PARTY_PREPARING:
            await ctx.send("Start a queue with `/queue start` first.", ephemeral=True)
            return
        if party.get("captain_discord_id") != ctx.author.id:
            await ctx.send("Only the captain can post.", ephemeral=True)
            return

        post, message = post_party_to_billboard(party, looking_for)
        if not post:
            await ctx.send(message, ephemeral=True)
            return

        party = get_party(party["party_id"])
        await refresh_war_billboard_posts(self.bot, board_for_party(party), post)
        await self._refresh_lobby_message(party)
        await ctx.send(message, ephemeral=True)

    @slash_command(
        name="queue",
        description="Team queue",
        sub_cmd_name="status",
        sub_cmd_description="View your lobby and hub post.",
        scopes=SCOPES,
    )
    async def queue_status(self, ctx: SlashContext):
        party = get_active_party_for_user(ctx.author.id)
        if not party:
            await ctx.send("You are not in an active queue party.", ephemeral=True)
            return

        post = None
        if party.get("match_post_id"):
            found = find_post_by_party_id(party["party_id"])
            if found:
                _, post = found
        await ctx.send(embeds=build_queue_status_embed(party, post), ephemeral=True)

    @slash_command(
        name="queue",
        description="Team queue",
        sub_cmd_name="cancel",
        sub_cmd_description="Captain cancels the team queue.",
        scopes=SCOPES,
    )
    async def queue_cancel(self, ctx: SlashContext):
        party = get_active_party_for_user(ctx.author.id)
        if not party:
            await ctx.send("No active queue to cancel.", ephemeral=True)
            return
        if party.get("captain_discord_id") != ctx.author.id:
            await ctx.send("Only the captain can cancel.", ephemeral=True)
            return

        cancel_party(party["party_id"])
        if party.get("lobby_message_id") and party.get("lobby_channel_id"):
            try:
                channel = await self.bot.fetch_channel(party["lobby_channel_id"])
                message = await channel.fetch_message(party["lobby_message_id"])
                await message.delete()
            except Exception:
                pass
        await ctx.send("Queue cancelled.", ephemeral=True)


def setup(bot: interactions.Client):
    QueueCommands(bot)
