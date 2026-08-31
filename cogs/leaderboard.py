import os
import re

import interactions
from interactions import (
    ActionRow,
    Button,
    ButtonStyle,
    ComponentContext,
    Extension,
    SlashContext,
    component_callback,
    slash_command,
    slash_option,
)

from utils.colors import COLORS
from utils.config import SCOPES
from utils.leaderboard import fetch_leaderboard

DISCORD_SCOPE = "elite"
PAGE_SIZE = 10


def _page_count(total: int, page_size: int) -> int:
    if total <= 0:
        return 1
    return (total + page_size - 1) // page_size


def _build_leaderboard_embed(board: dict, *, page: int, page_size: int) -> interactions.Embed:
    track_u = board["track"].upper()
    role_l = board["role"].capitalize()
    total = int(board.get("total") or 0)
    pages = _page_count(total, page_size)
    title = f"{track_u} {role_l} · {board['scope_label']}"

    lines: list[str] = []
    for entry in board.get("entries") or []:
        rank = entry.get("rank")
        name = entry.get("display_name") or "?"
        sr = entry.get("sr")
        tier = str(entry.get("rank_tier") or "").replace("_", " ").title()
        lines.append(f"**{rank}.** {name} — {sr} SR ({tier})")

    body = "\n".join(lines) if lines else "_No Ruby+ players on this board yet._"
    embed = interactions.Embed(
        title=title,
        description=body[:4000],
        color=COLORS["default"],
    )
    embed.set_footer(
        text=f"Page {page + 1} of {pages} · Full rankings on the website"
    )
    return embed


def _build_leaderboard_components(track: str, role: str, *, page: int, total: int) -> list[ActionRow]:
    max_page = max(0, _page_count(total, PAGE_SIZE) - 1)
    nav = ActionRow(
        Button(
            style=ButtonStyle.SECONDARY,
            label="<",
            custom_id=f"lb_nav:prev:{track}:{role}:{page}",
            disabled=page <= 0,
        ),
        Button(
            style=ButtonStyle.SECONDARY,
            label=">",
            custom_id=f"lb_nav:next:{track}:{role}:{page}",
            disabled=page >= max_page,
        ),
    )
    rows: list[ActionRow] = [nav]

    web = os.getenv("WEB_BASE_URL", "http://localhost:3000").rstrip("/")
    if web:
        rows.append(
            ActionRow(
                Button(
                    style=ButtonStyle.URL,
                    label="Open full leaderboard",
                    url=f"{web}/leaderboard?track={track}&role={role}",
                )
            )
        )
    return rows


def _render_leaderboard_page(track: str, role: str, page: int) -> tuple[interactions.Embed, list[ActionRow]]:
    board = fetch_leaderboard(
        track=track,
        role=role,
        scope=DISCORD_SCOPE,
        limit=PAGE_SIZE,
        offset=page * PAGE_SIZE,
    )
    embed = _build_leaderboard_embed(board, page=page, page_size=PAGE_SIZE)
    components = _build_leaderboard_components(
        board["track"],
        board["role"],
        page=page,
        total=int(board.get("total") or 0),
    )
    return embed, components


class LeaderboardCommands(Extension):
    @slash_command(
        name="leaderboard",
        description="Ruby+ elite SR leaderboard for a track and role.",
        scopes=SCOPES,
    )
    @slash_option(
        name="track",
        description="RT or CT lane",
        opt_type=interactions.OptionType.STRING,
        choices=[
            interactions.SlashCommandChoice(name="Regular Tracks (RT)", value="rt"),
            interactions.SlashCommandChoice(name="Custom Tracks (CT)", value="ct"),
        ],
        required=False,
    )
    @slash_option(
        name="role",
        description="Runner or bagger lane",
        opt_type=interactions.OptionType.STRING,
        choices=[
            interactions.SlashCommandChoice(name="Runner", value="runner"),
            interactions.SlashCommandChoice(name="Bagger", value="bagger"),
        ],
        required=False,
    )
    async def leaderboard(
        self,
        ctx: SlashContext,
        track: str = "rt",
        role: str = "runner",
    ):
        await ctx.defer(ephemeral=False)
        embed, components = _render_leaderboard_page(track, role, page=0)
        await ctx.send(embeds=embed, components=components)

    @component_callback(re.compile(r"^lb_nav:(prev|next):(rt|ct):(runner|bagger):(\d+)$"))
    async def leaderboard_nav(self, ctx: ComponentContext):
        match = re.match(r"^lb_nav:(prev|next):(rt|ct):(runner|bagger):(\d+)$", ctx.custom_id)
        if not match:
            return
        direction, track, role, page_raw = match.groups()
        page = max(0, int(page_raw))
        if direction == "prev":
            page = max(0, page - 1)
        else:
            page += 1

        try:
            embed, components = _render_leaderboard_page(track, role, page=page)
            await ctx.message.edit(embeds=embed, components=components)
        except Exception as exc:
            print(f"❌ leaderboard_nav failed: {exc}")
            await ctx.send("Couldn't update the leaderboard page.", ephemeral=True)


def setup(bot: interactions.Client):
    LeaderboardCommands(bot)
