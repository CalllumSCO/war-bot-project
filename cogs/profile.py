import os

import interactions
from interactions import (
    ActionRow,
    Button,
    ButtonStyle,
    Extension,
    File,
    Modal,
    ShortText,
    SlashContext,
    listen,
    slash_command,
)

from utils.config import SCOPES
from utils.discord_defer import defer_ephemeral, send_ephemeral
from utils.embeds import build_profile_embed
from utils.player_links import link_manual_friend_code, resolve_friend_code, try_lounge_link
from utils.player_profile_store import get_profile
from utils.player_store import get_player
from utils.profile_view import recent_wars_for_profile, resolve_profile_team
from utils.rank_icons import icon_url, local_rank_path, warm_rank_icon_cache


class ProfileCommands(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @listen()
    async def on_startup(self):
        await warm_rank_icon_cache(self.bot)

    @slash_command(
        name="profile",
        description="Link your Wii friend code",
        sub_cmd_name="link",
        sub_cmd_description="Link Lounge account or enter your WiimmFI FC.",
        scopes=SCOPES,
    )
    async def profile_link(self, ctx: SlashContext):
        # Auto-link is optional — any Lounge/API failure just falls through to manual FC.
        try:
            profile, lounge_player, lounge_error = await try_lounge_link(ctx.author.id)
        except Exception:
            profile, lounge_player, lounge_error = None, None, None

        if profile:
            name = profile.get("lounge_name")
            name_part = f" as **{name}**" if name else ""
            await ctx.send(
                f"Linked your **Lounge** account{name_part}.\n"
                f"**FC:** `{profile.get('friend_code')}`\n"
                "Run `/profile view` anytime to see ratings and recent form.",
                ephemeral=True,
            )
            return

        # Discord: modal must be the initial response — don't send a message first.
        lounge_name = None
        if lounge_player:
            lounge_name = lounge_player.get("player_name") or lounge_player.get("name")

        if lounge_name:
            title = f"FC for Lounge: {lounge_name}"
        else:
            title = "Link friend code"
        if len(title) > 45:
            title = "Link friend code"

        modal = Modal(
            ShortText(
                label="WiimmFI friend code",
                custom_id="friend_code",
                placeholder="1234-5678-9012",
                required=True,
                max_length=14,
            ),
            title=title,
        )
        await ctx.send_modal(modal)
        m_ctx = await self.bot.wait_for_modal(modal, ctx.author)
        linked, error = await link_manual_friend_code(
            ctx.author.id,
            m_ctx.kwargs.get("friend_code", ""),
            lounge_player=lounge_player,
        )
        if error:
            await m_ctx.send(error, ephemeral=True)
            return

        if lounge_name:
            await m_ctx.send(
                f"Linked **Lounge** account **{lounge_name}** with FC `{linked.get('friend_code')}`.\n"
                "Lounge found your Discord account, but no FC was stored there — saved yours manually.\n"
                "Run `/profile view` to see your card.",
                ephemeral=True,
            )
        elif lounge_error:
            await m_ctx.send(
                f"Friend code saved: `{linked.get('friend_code')}`\n"
                "Lounge lookup wasn’t available, so this is a manual FC link "
                "(still enough for wars).\n"
                "If you later link Discord on Lounge, run `/profile link` again.\n"
                "Run `/profile view` to see your card.",
                ephemeral=True,
            )
        else:
            await m_ctx.send(
                f"Friend code saved: `{linked.get('friend_code')}`\n"
                "No Lounge account was found for your Discord ID. "
                "If you later link Discord on Lounge, run `/profile link` again.\n"
                "Run `/profile view` to see your card.",
                ephemeral=True,
            )

    @slash_command(
        name="profile",
        description="Link your Wii friend code",
        sub_cmd_name="view",
        sub_cmd_description="View your ratings, FC, team, and recent wars.",
        scopes=SCOPES,
    )
    async def profile_view(self, ctx: SlashContext):
        await defer_ephemeral(ctx)
        await warm_rank_icon_cache(self.bot, force=True)

        profile = get_profile(ctx.author.id)
        fc = (profile or {}).get("friend_code")
        if not fc:
            guild_id = ctx.guild.id if ctx.guild else None
            fc = await resolve_friend_code(ctx.author.id, guild_id=guild_id)
            profile = get_profile(ctx.author.id) or profile

        if not profile and not fc:
            await send_ephemeral(ctx, "No profile linked yet. Run `/profile link` first.")
            return

        if profile and fc and not profile.get("friend_code"):
            profile = {**profile, "friend_code": fc}
        elif not profile and fc:
            profile = {"friend_code": fc, "link_source": "resolved"}

        guild_id = ctx.guild.id if ctx.guild else None
        team, team_mmr = resolve_profile_team(guild_id)
        avatar = None
        try:
            avatar = ctx.author.avatar.url if ctx.author.avatar else None
        except Exception:
            avatar = None

        embed, top_rank = build_profile_embed(
            display_name=ctx.author.display_name,
            discord_id=ctx.author.id,
            avatar_url=avatar,
            profile=profile,
            player=get_player(ctx.author.id),
            team=team,
            team_mmr=team_mmr,
            recent=recent_wars_for_profile(ctx.author.id, limit=5),
        )

        files = []
        # Local assets are the reliable thumbnail source; Discord role CDN is a bonus.
        path = local_rank_path(top_rank)
        if path is not None:
            files.append(File(path))
            embed.set_thumbnail(url=f"attachment://{path.name}")
        elif icon_url(top_rank):
            embed.set_thumbnail(url=icon_url(top_rank))

        web_base = (os.getenv("WEB_BASE_URL") or "http://localhost:3000").rstrip("/")
        profile_url = f"{web_base}/u/{ctx.author.id}"
        components = [
            ActionRow(
                Button(
                    style=ButtonStyle.URL,
                    label="Open web profile",
                    url=profile_url,
                )
            )
        ]
        await send_ephemeral(
            ctx,
            embeds=embed,
            components=components,
            files=files or None,
        )


def setup(bot: interactions.Client):
    ProfileCommands(bot)
