import os
from typing import Any, Dict, List, Optional

import interactions

from utils.colors import COLORS
from utils.mmr import format_average_rank
from classes.queue_party import MODE_CASUAL
from utils.roster import (
    SEARCH_ALLIES,
    SEARCH_OPPONENTS,
    can_seek_opponents,
    format_lineup,
    party_status_label,
    roster_summary,
    status_label,
)


def _track_color(war_type: str) -> int:
    return COLORS["ct"] if war_type.upper() == "CT" else COLORS["rt"]


def _embed_color(war: Dict[str, Any]) -> int:
    status = war.get("status", "open")
    search_mode = war.get("search_mode", SEARCH_ALLIES)
    lineup = war.get("lineup", [])

    if status == "matched":
        return COLORS["matched"]
    if search_mode == SEARCH_OPPONENTS and can_seek_opponents(lineup):
        return COLORS["opponents"]
    return COLORS["allies"]


def build_war_embed(war: Dict[str, Any]) -> interactions.Embed:
    from utils.search_time import format_search_time, opponent_search_unlocked

    war_type = war.get("war_type", "RT").upper()
    lineup = war.get("lineup", [])
    search_mode = war.get("search_mode", SEARCH_ALLIES)
    status = war.get("status", "open")
    mode = war.get("mode", "ranked")
    label = status_label(search_mode, status, lineup)
    search_time = war.get("start_time", "ASAP")
    unlocked = opponent_search_unlocked(
        search_time,
        created_at=war.get("created_at") or war.get("last_updated"),
    )

    embed = interactions.Embed(
        title=f"{war.get('team_name', 'Unknown Team')} — {war_type} · {mode.title()}",
        description=f"**{label}**",
        color=_embed_color(war),
    )

    embed.add_field(
        name="Search time",
        value=format_search_time(search_time),
        inline=True,
    )

    embed.add_field(
        name="Roster",
        value=roster_summary(lineup),
        inline=False,
    )

    if mode == MODE_CASUAL:
        embed.add_field(
            name=f"Lineup ({len(lineup)}/5)",
            value=format_lineup(lineup),
            inline=False,
        )
    else:
        embed.add_field(
            name="Team rank",
            value=format_average_rank(lineup, war_type),
            inline=False,
        )

    matched = war.get("matched_opponent")
    if matched and status == "matched":
        embed.add_field(
            name="Opponent",
            value=(
                f"**{matched.get('team_name', 'Unknown')}**\n"
                f"Accepted by <@{matched.get('author_discord_id', '0')}>"
            ),
            inline=False,
        )

    if search_mode == SEARCH_ALLIES and status == "open":
        if can_seek_opponents(lineup) and not unlocked:
            embed.add_field(
                name="Scheduled",
                value=f"Full roster ready. Opponent search opens at **{format_search_time(search_time)}**.",
                inline=False,
            )
        elif not can_seek_opponents(lineup):
            embed.add_field(
                name="Looking for allies",
                value="Need a full roster with at least one bagger before opponent search.",
                inline=False,
            )

    embed.set_footer(text="War Bot")
    return embed


def build_queue_party_embed(party: Dict[str, Any]) -> interactions.Embed:
    from utils.search_time import format_search_time, opponent_search_unlocked

    war_type = party.get("war_type", "RT").upper()
    lineup = party.get("lineup", [])
    status = party.get("status", "preparing")
    label = party_status_label(status)
    search_time = party.get("search_time", "ASAP")
    unlocked = opponent_search_unlocked(
        search_time,
        created_at=party.get("created_at") or party.get("last_updated"),
    )

    embed = interactions.Embed(
        title=f"{party.get('team_name', 'Unknown Team')} — queue",
        description=(
            f"**{label}**\n"
            f"{war_type} · {party.get('mode', 'ranked').title()} · {format_search_time(search_time)}"
        ),
        color=COLORS["waiting"] if status == "preparing" else COLORS["opponents"],
    )

    embed.add_field(
        name="Roster",
        value=roster_summary(lineup),
        inline=False,
    )

    embed.add_field(
        name=f"Lineup ({len(lineup)}/5)",
        value=format_lineup(lineup),
        inline=False,
    )

    if status == "preparing":
        tip = "Teammates join here. Captain posts when ready (needs a bagger)."
        if party.get("mode") == MODE_CASUAL and not unlocked:
            tip += (
                f" You can look for allies anytime; opponent search opens at "
                f"**{format_search_time(search_time)}**."
            )
        embed.add_field(name="Next step", value=tip, inline=False)
    elif status == "posted":
        if party.get("search_mode") == SEARCH_OPPONENTS:
            tip = "Live on the hub — looking for opponents."
        elif can_seek_opponents(lineup) and not unlocked:
            tip = (
                f"Posted for allies. Opponent search opens at "
                f"**{format_search_time(search_time)}**."
            )
        else:
            tip = "Posted on the hub for allies. Teammates can still join here."
        embed.add_field(name="Hub", value=tip, inline=False)

    embed.set_footer(text="War Bot · team queue")
    return embed


def build_queue_status_embed(party: Dict[str, Any], post: Optional[Dict[str, Any]] = None) -> interactions.Embed:
    embed = build_queue_party_embed(party)
    embed.title = f"Your Queue — {party.get('team_name', 'Unknown Team')}"
    if post:
        embed.add_field(
            name="📌 Hub post",
            value=status_label(post.get("search_mode", "allies"), post.get("status", "open"), post.get("lineup", [])),
            inline=False,
        )
    return embed


def build_war_view_embed(war: Dict[str, Any], *, is_owner: bool) -> interactions.Embed:
    embed = build_war_embed(war)
    embed.title = f"Hub Post — {war.get('team_name', 'Unknown Team')}"
    if is_owner:
        embed.description = (
            f"{embed.description}\n\n"
            "Manage this post from the hub billboard buttons."
        )
    return embed


def build_setup_embed(
    guild_name: str,
    config: Optional[Dict[str, Any]],
    *,
    title: str,
    description: str,
    error: bool = False,
) -> interactions.Embed:
    embed = interactions.Embed(
        title=title,
        description=description,
        color=COLORS["error"] if error else COLORS["default"],
    )

    if config:
        embed.add_field(
            name="RT Ranked",
            value=f"<#{config['rt_ranked_channel_id']}>" if config.get("rt_ranked_channel_id") else "Not linked",
            inline=True,
        )
        embed.add_field(
            name="RT Casual",
            value=f"<#{config['rt_casual_channel_id']}>" if config.get("rt_casual_channel_id") else "Not linked",
            inline=True,
        )
        embed.add_field(
            name="CT Ranked",
            value=f"<#{config['ct_ranked_channel_id']}>" if config.get("ct_ranked_channel_id") else "Not linked",
            inline=True,
        )
        embed.add_field(
            name="CT Casual",
            value=f"<#{config['ct_casual_channel_id']}>" if config.get("ct_casual_channel_id") else "Not linked",
            inline=True,
        )
        embed.add_field(
            name="Team Queue Channel",
            value=f"<#{config['queue_channel_id']}>" if config.get("queue_channel_id") else "Not linked",
            inline=True,
        )
        auto_on = True if "auto_invite_allies" not in config else bool(config.get("auto_invite_allies"))
        ally_role = config.get("ally_role_id")
        if auto_on:
            auto_value = f"On (default) · role <@&{ally_role}>" if ally_role else "On (default)"
        else:
            auto_value = "Off — toggle with `/config`"
        embed.add_field(
            name="Auto-invite allies",
            value=auto_value,
            inline=True,
        )
        if config.get("how_to_use_channel_id"):
            from utils.guild_config_schema import HOW_TO_GUIDE_VERSION, get_how_to_guide_version, how_to_guide_outdated

            howto_v = get_how_to_guide_version(config)
            howto_value = f"<#{config['how_to_use_channel_id']}> · guide v{howto_v}"
            if how_to_guide_outdated(config):
                howto_value += f" (v{HOW_TO_GUIDE_VERSION} available — `/config action:Check for updates`)"
            embed.add_field(
                name="How To Use",
                value=howto_value,
                inline=False,
            )
        if config.get("category_id"):
            embed.add_field(
                name="Category ID",
                value=f"`{config['category_id']}`",
                inline=False,
            )

    embed.set_footer(text=f"War Bot setup · {guild_name}")
    return embed


def build_how_to_use_embeds() -> list:
    """Guide posted into each server's #how-to-use channel (multiple embeds)."""
    web_base = (os.getenv("WEB_BASE_URL") or "http://localhost:3000").rstrip("/")
    web_info = f"{web_base}/q/info"

    intro = interactions.Embed(
        title="How to use War Bot",
        description=(
            "MKWii **5v5** war matchmaking — Discord + companion web app.\n\n"
            f"Full web guide (queue + ranked system): **{web_info}**"
        ),
        color=COLORS["default"],
    )
    intro.add_field(
        name="Quick start",
        value=(
            "1. Admin: `/team` then `/setup` (and `/config` for preferences)\n"
            "2. Everyone: `/profile link`\n"
            "3. Captain: `/queue start` → lobby → **Post to Hub** / `/queue post`\n"
            "4. Hub: **Request Ally** or **Request Match**\n"
            "5. Finish in `war-vs-*` with `/war complete`"
        ),
        inline=False,
    )
    intro.add_field(
        name="Companion site",
        value=(
            f"Queue, invites, and profiles on the web: {web_base}/q\n"
            f"How to use (web): {web_info}"
        ),
        inline=False,
    )

    match_chat = interactions.Embed(
        title="Match chat · blue embeds",
        description=(
            "Messages **without** a team prefix are **match chat** (blue).\n"
            "Both teams see them in their `war-vs-*` channels and on the web."
        ),
        color=COLORS["match_chat"],
    )
    group_chat = interactions.Embed(
        title="Group chat · green embeds",
        description=(
            "Start a message with **`g:`** or **`.g `** for **team-only** chat (green).\n"
            "Example: `g: let's bag mid`\n\n"
            "Only your roster sees it — use this for strategy / FC / host notes."
        ),
        color=COLORS["group_chat"],
    )

    allies = interactions.Embed(
        title="Allies & auto-invite",
        description=(
            "When someone is accepted as an ally and they aren't in this Discord yet, "
            "War Bot can DM them a **one-time, 1-hour** invite. Joining grants the "
            "**War Bot Ally** role for `#team-queue` access."
        ),
        color=COLORS["allies"],
    )
    allies.add_field(
        name="Config",
        value=(
            "Auto-invite is **on by default** after `/setup`.\n"
            "Admins: `/config` → **Auto-invite allies** → On/Off\n"
            "Private servers can turn it off anytime."
        ),
        inline=False,
    )
    allies.add_field(
        name="Config updates",
        value=(
            "After War Bot updates: `/config action:Check for updates`\n"
            "Review new toggles, **Keep defaults**, or refresh this channel."
        ),
        inline=False,
    )
    allies.add_field(
        name="More help",
        value="`/help queue` · `/help war` · `/help billboard` · `/help setup`",
        inline=False,
    )
    allies.set_footer(text="War Bot")
    return [intro, match_chat, group_chat, allies]


def build_how_to_use_embed() -> interactions.Embed:
    """Back-compat single embed (first of the how-to set)."""
    return build_how_to_use_embeds()[0]


def build_profile_embed(
    *,
    display_name: str,
    discord_id: int,
    avatar_url: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
    player: Optional[Dict[str, Any]] = None,
    team: Optional[Dict[str, Any]] = None,
    team_mmr: Optional[int] = None,
    recent: Optional[List[Dict[str, Any]]] = None,
) -> tuple[interactions.Embed, str]:
    """
    Build the /profile view embed.

    Returns (embed, top_rank_key) so the caller can attach a local rank icon file.
    """
    from utils.player_store import get_player
    from utils.rank_icons import emoji_mention, icon_url
    from utils.sr import get_player_rating, tier_label

    profile = profile or {}
    player = player or get_player(discord_id)

    web_base = (os.getenv("WEB_BASE_URL") or "http://localhost:3000").rstrip("/")
    profile_url = f"{web_base}/u/{discord_id}"

    lounge_name = profile.get("lounge_name")
    title_name = "Profile — " + (lounge_name if lounge_name else display_name)
    fc = profile.get("friend_code")
    fc_line = f"**Friend code:** `{fc}`" if fc else "**Friend code:** Not linked"

    embed = interactions.Embed(
        title=title_name,
        description=(
            f"<@{discord_id}>"
            + (f" · Lounge **{lounge_name}**" if lounge_name else "")
            + f"\n{fc_line}"
        ),
        color=COLORS["default"],
        url=profile_url,
    )
    if avatar_url:
        embed.set_author(name=display_name, icon_url=avatar_url, url=profile_url)

    def _lane(track: str, role: str, *, bagger: bool) -> tuple[str, Optional[str]]:
        """Return (display cell, rank key for icon)."""
        try:
            rating = get_player_rating(discord_id, track.upper(), bagger=bagger, role=role)
        except Exception:
            rating = None
        if not rating:
            return "Unranked", "unranked"
        rank_key = str(rating.get("rank") or "unranked").lower()
        emoji = emoji_mention(rank_key)
        prefix = f"{emoji} " if emoji else ""
        if not rating.get("revealed"):
            placed = int(rating.get("placement_count") or 0)
            return f"{prefix}Unranked ({placed}/5)", "unranked"
        sr = int(rating.get("sr") or 0)
        label = tier_label(rank_key)
        return f"{prefix}`{sr:,}` {label}", rank_key

    rt_run, rt_run_rank = _lane("rt", "runner", bagger=False)
    rt_bag, rt_bag_rank = _lane("rt", "bagger", bagger=True)
    ct_run, ct_run_rank = _lane("ct", "runner", bagger=False)
    ct_bag, ct_bag_rank = _lane("ct", "bagger", bagger=True)

    # Prefer the highest revealed lane for the thumbnail icon.
    rank_priority = (
        "paragon",
        "ruby",
        "emerald",
        "diamond",
        "platinum",
        "gold",
        "silver",
        "bronze",
        "iron",
        "unranked",
    )
    top_rank = "unranked"
    for candidate in (rt_run_rank, rt_bag_rank, ct_run_rank, ct_bag_rank):
        if not candidate or candidate not in rank_priority:
            continue
        if rank_priority.index(candidate) < rank_priority.index(top_rank):
            top_rank = candidate

    # Prefer Discord role/emoji CDN; caller attaches local file if this is missing.
    thumb = icon_url(top_rank)
    if thumb:
        embed.set_thumbnail(url=thumb)

    embed.add_field(
        name="SR",
        value=(
            f"**RT** Run {rt_run} · Bag {rt_bag}\n"
            f"**CT** Run {ct_run} · Bag {ct_bag}"
        ),
        inline=False,
    )

    overall_w = int(player.get("wins", 0))
    overall_l = int(player.get("losses", 0))
    embed.add_field(
        name="Overall",
        value=f"**{overall_w}W – {overall_l}L**",
        inline=True,
    )

    recent = recent or []
    if recent:
        lines = []
        for row in recent[:2]:
            outcome = row.get("player_outcome", "?")
            war_type = str(row.get("war_type", "RT")).upper()
            if outcome == "W":
                opponent = row.get("loser_team_name", "Unknown")
                sign = "+"
            else:
                opponent = row.get("winner_team_name", "Unknown")
                sign = "−"
            margin = row.get("point_margin", "?")
            delta = (row.get("player_mmr_deltas") or {}).get(str(discord_id))
            delta_txt = ""
            if isinstance(delta, int):
                try:
                    from utils.sr import get_player_rating as _gpr

                    entry = row.get("player_entry") or {}
                    is_bag = bool(entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger")
                    rating = _gpr(
                        discord_id,
                        war_type,
                        bagger=is_bag,
                        role="bagger" if is_bag else "runner",
                    )
                    if rating.get("revealed"):
                        delta_txt = f" · SR `{delta:+d}`"
                except Exception:
                    pass
            lines.append(
                f"**{outcome}** {war_type} vs **{opponent}** ({sign}{margin}){delta_txt}"
            )
        embed.add_field(name="Recent", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Web profile · {profile_url}")
    return embed, top_rank


def build_match_request_embed(requester_war: Dict[str, Any]) -> interactions.Embed:
    mode = requester_war.get("mode", "ranked")
    lineup = requester_war.get("lineup", [])
    embed = interactions.Embed(
        title=f"⚔️ Match request — {requester_war.get('team_name', 'Unknown Team')}",
        description=(
            f"**{requester_war.get('team_name')}** wants to war your team.\n"
            f"**Track:** {requester_war.get('war_type', 'RT')} · **Mode:** {mode.title()}\n"
            f"**Search time:** `{requester_war.get('start_time', 'ASAP')}`"
        ),
        color=COLORS["opponents"],
    )
    if mode == MODE_CASUAL:
        embed.add_field(name="👥 Their lineup", value=format_lineup(lineup), inline=False)
    else:
        embed.add_field(
            name="📊 Their team rank",
            value=format_average_rank(lineup, requester_war.get("war_type", "RT")),
            inline=False,
        )
    embed.set_footer(text="War Bot · Accept or decline below")
    return embed
