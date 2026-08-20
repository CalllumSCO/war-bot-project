import re
from typing import Any, Dict, List, Optional

import interactions
from interactions import PermissionOverwrite, Permissions

from utils.billboard_store import upsert_war
from utils.boards import board_key as board_for_war
from utils.guild_config import get_guild_config
from utils.match_request_store import create_request, pending_for_target_war
from utils.match_session_store import create_session
from utils.mmr import team_roster_players
from utils.match_posting import sync_party_lineup_from_post
from utils.queue_store import get_party, upsert_party
from classes.queue_party import PARTY_POSTED
from datetime import datetime


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:20] or "team"


def roster_member_ids(war: Dict[str, Any]) -> List[int]:
    ids = []
    for player in team_roster_players(war.get("lineup", [])):
        discord_id = player.get("discord_id")
        if discord_id and int(discord_id) not in ids:
            ids.append(int(discord_id))
    return ids


def _touch_war(war: Dict[str, Any]) -> Dict[str, Any]:
    war["last_updated"] = datetime.utcnow().isoformat()
    war["ally_count"] = sum(1 for player in war.get("lineup", []) if player.get("ally"))
    return war


def _sync_parties(board: str, war_a: Dict[str, Any], war_b: Dict[str, Any]) -> None:
    for war in (war_a, war_b):
        party_id = war.get("party_id")
        if not party_id:
            continue
        party = get_party(party_id)
        if party:
            upsert_party(sync_party_lineup_from_post(party, war))


def finalize_match(board: str, target_war: Dict[str, Any], requester_war: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    target_war["status"] = "matched"
    target_war["matched_opponent"] = {
        "war_id": requester_war.get("war_id"),
        "team_name": requester_war.get("team_name"),
        "author_discord_id": requester_war.get("author_discord_id"),
    }
    requester_war["status"] = "matched"
    requester_war["matched_opponent"] = {
        "war_id": target_war.get("war_id"),
        "team_name": target_war.get("team_name"),
        "author_discord_id": target_war.get("author_discord_id"),
    }
    target_war = _touch_war(target_war)
    requester_war = _touch_war(requester_war)
    upsert_war(board, target_war)
    upsert_war(board, requester_war)
    _sync_parties(board, target_war, requester_war)
    return target_war, requester_war


def reopen_wars_after_failed_accept(
    board: str,
    target_war: Dict[str, Any],
    requester_war: Dict[str, Any],
) -> None:
    """Best-effort rollback if accept failed after wars were finalized."""
    for war in (target_war, requester_war):
        war["status"] = "open"
        war.pop("matched_opponent", None)
        war = _touch_war(war)
        upsert_war(board, war)
        party_id = war.get("party_id")
        if not party_id:
            continue
        party = get_party(party_id)
        if not party:
            continue
        party["status"] = PARTY_POSTED
        party["search_mode"] = war.get("search_mode") or party.get("search_mode") or "opponents"
        party["match_post_id"] = war.get("war_id")
        upsert_party(party)


async def _channel_overwrites(
    guild,
    member_ids: List[int],
    bot: interactions.Client,
) -> List[PermissionOverwrite]:
    everyone = PermissionOverwrite.for_target(guild.default_role)
    everyone.add_denies(Permissions.VIEW_CHANNEL)

    me = guild.me
    if me is None:
        try:
            me = await guild.fetch_member(int(bot.user.id))
        except Exception:
            me = bot.user
    bot_overwrite = PermissionOverwrite.for_target(me)
    bot_overwrite.add_allows(
        Permissions.VIEW_CHANNEL,
        Permissions.SEND_MESSAGES,
        Permissions.EMBED_LINKS,
        Permissions.READ_MESSAGE_HISTORY,
        Permissions.MANAGE_CHANNELS,
    )

    overwrites = [everyone, bot_overwrite]
    for member_id in member_ids:
        try:
            member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        except Exception:
            continue
        if member is None:
            continue
        overwrite = PermissionOverwrite.for_target(member)
        overwrite.add_allows(
            Permissions.VIEW_CHANNEL,
            Permissions.SEND_MESSAGES,
            Permissions.READ_MESSAGE_HISTORY,
        )
        overwrites.append(overwrite)
    return overwrites


def _origin_guild_id(war: Dict[str, Any]) -> Optional[int]:
    try:
        gid = int(war.get("origin_guild_id") or 0)
    except (TypeError, ValueError):
        return None
    return gid or None


def _match_intro(opponent_name: str) -> str:
    return (
        f"**Match confirmed** vs **{opponent_name}**.\n"
        "Chat here — messages relay to the other team's war channel.\n\n"
        "**Before finishing:** everyone on the roster should `/profile link`.\n\n"
        "**Captain commands (this channel only):**\n"
        "• `/war complete` — report won/lost + margin + **RXX** (scores auto-load from room)\n"
        "• `/war scores` — manual fallback only if RXX lookup fails\n"
        "• `/war confirm` / `/war dispute` — both captains confirm\n"
        "• `/war cancel` — request abort (opponent `/war approve-cancel`)"
    )


async def create_war_comm_channels(
    bot: interactions.Client,
    board: str,
    target_war: Dict[str, Any],
    requester_war: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    roster_a = roster_member_ids(target_war)
    roster_b = roster_member_ids(requester_war)
    if not roster_a or not roster_b:
        return None

    gid_a = _origin_guild_id(target_war)
    gid_b = _origin_guild_id(requester_war)
    if not gid_a and not gid_b:
        return None

    short = target_war.get("war_id", "")[:6]
    channel_a = None
    channel_b = None

    if gid_a:
        try:
            guild_a = await bot.fetch_guild(gid_a)
            config_a = get_guild_config(guild_a.id) or {}
            category_a = config_a.get("category_id")
            if category_a is not None:
                category_a = int(category_a)
            channel_a = await guild_a.create_text_channel(
                name=f"war-vs-{_slug(requester_war.get('team_name', 'team'))}-{short}",
                category=category_a,
                permission_overwrites=await _channel_overwrites(guild_a, roster_a, bot),
                topic=f"War comms vs {requester_war.get('team_name')} — messages relay to their server",
            )
            await channel_a.send(_match_intro(requester_war.get("team_name")))
        except Exception as exc:
            print(f"❌ create_war_comm_channels guild_a failed: {exc}")
            return None
    if gid_b:
        try:
            guild_b = await bot.fetch_guild(gid_b)
            config_b = get_guild_config(guild_b.id) or {}
            category_b = config_b.get("category_id")
            if category_b is not None:
                category_b = int(category_b)
            channel_b = await guild_b.create_text_channel(
                name=f"war-vs-{_slug(target_war.get('team_name', 'team'))}-{short}",
                category=category_b,
                permission_overwrites=await _channel_overwrites(guild_b, roster_b, bot),
                topic=f"War comms vs {target_war.get('team_name')} — messages relay to their server",
            )
            await channel_b.send(_match_intro(target_war.get("team_name")))
        except Exception as exc:
            # Web requesters often have no usable Discord guild channel — target-side only is OK.
            print(f"❌ create_war_comm_channels guild_b failed: {exc}")

    if channel_a is None and channel_b is None:
        return None

    try:
        return create_session(
            board,
            target_war,
            requester_war,
            channel_a.id if channel_a is not None else 0,
            channel_b.id if channel_b is not None else 0,
            roster_a,
            roster_b,
        )
    except Exception as exc:
        print(f"❌ create_war_comm_channels session persist failed: {exc}")
        for ch in (channel_a, channel_b):
            if ch is None:
                continue
            try:
                await ch.delete(reason="Match accept rollback — session not saved")
            except Exception:
                pass
        return None


def start_match_request(board: str, target_war_id: str, requester_war_id: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if pending_for_target_war(target_war_id):
        return None, "This team already has a pending match request."
    request = create_request(board, target_war_id, requester_war_id)
    return request, None


def board_for_party(party: Dict[str, Any]) -> str:
    return board_for_war(party.get("war_type", "RT"), party.get("mode", "ranked"))
