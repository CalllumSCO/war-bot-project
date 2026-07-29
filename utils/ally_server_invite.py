"""Auto-invite accepted allies into the posting team's Discord server."""

from __future__ import annotations

from typing import Any, Dict, Optional

import interactions

from utils.guild_config import (
    get_guild_config,
    get_queue_channel_id,
    is_auto_invite_allies_enabled,
    upsert_guild_config,
)
from utils.pending_ally_joins import remember_pending_ally_join

ALLY_ROLE_NAME = "War Bot Ally"
INVITE_MAX_AGE_SECONDS = 3600  # 1 hour, single-use


async def ensure_ally_role(guild: interactions.Guild, config: Dict[str, Any]) -> Optional[interactions.Role]:
    """Create/fetch the Ally role and grant it access to #team-queue."""
    role_id = config.get("ally_role_id")
    role = None
    if role_id:
        try:
            role = await guild.fetch_role(int(role_id))
        except Exception:
            role = None

    if role is None:
        # Prefer an existing role with the same name.
        for existing in guild.roles or []:
            if existing.name == ALLY_ROLE_NAME:
                role = existing
                break

    if role is None:
        try:
            role = await guild.create_role(
                name=ALLY_ROLE_NAME,
                reason="War Bot auto-invite allies",
                mentionable=False,
            )
        except Exception as exc:
            print(f"❌ Could not create Ally role in {guild.id}: {exc}")
            return None

    queue_channel_id = config.get("queue_channel_id") or get_queue_channel_id(guild.id)
    if queue_channel_id:
        try:
            channel = await guild.fetch_channel(int(queue_channel_id))
            await channel.set_permission(
                role,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                add_reactions=True,
                reason="War Bot Ally access to team-queue",
            )
        except Exception as exc:
            print(f"⚠️ Could not grant Ally role queue-channel perms: {exc}")

    # Persist role id only — do not force the toggle on/off here.
    upsert_guild_config(int(guild.id), guild.name, ally_role_id=int(role.id))
    return role


async def maybe_auto_invite_ally(
    bot: interactions.Client,
    war: Dict[str, Any],
    requester_discord_id: int,
    *,
    role_label: str = "Runner",
) -> Optional[str]:
    """
    If auto-invite is enabled for the war's origin guild (default ON when set up):
    - member already in guild → assign Ally role
    - otherwise → DM a 1-use / 1-hour invite and remember them for role grant on join

    Returns a short status note for logs / accept ephemerals, or None if skipped.
    """
    guild_id = war.get("origin_guild_id")
    if not guild_id:
        return None

    config = get_guild_config(int(guild_id))
    if not is_auto_invite_allies_enabled(config):
        return None

    try:
        guild = await bot.fetch_guild(int(guild_id))
    except Exception as exc:
        print(f"⚠️ auto-invite: fetch guild {guild_id} failed: {exc}")
        return None

    role_id = config.get("ally_role_id")
    role = None
    if role_id:
        try:
            role = await guild.fetch_role(int(role_id))
        except Exception:
            role = None
    if role is None:
        role = await ensure_ally_role(guild, config)
        if not role:
            return None
        config = get_guild_config(int(guild_id)) or config

    # Already a member?
    member = None
    try:
        member = await guild.fetch_member(int(requester_discord_id))
    except Exception:
        member = None

    team = war.get("team_name") or guild.name
    if member is not None:
        try:
            await member.add_role(role, reason="War Bot accepted ally")
        except Exception as exc:
            print(f"⚠️ auto-invite: add role failed: {exc}")
            return "Ally is already in the server (could not assign Ally role)."
        return f"Ally is already in the server — granted **{ALLY_ROLE_NAME}**."

    queue_channel_id = config.get("queue_channel_id") or get_queue_channel_id(int(guild_id))
    if not queue_channel_id:
        return "Auto-invite enabled but no team-queue channel is linked."

    try:
        channel = await bot.fetch_channel(int(queue_channel_id))
        invite = await channel.create_invite(
            max_age=INVITE_MAX_AGE_SECONDS,
            max_uses=1,
            unique=True,
            reason=f"War Bot ally invite for {requester_discord_id}",
        )
    except Exception as exc:
        print(f"❌ auto-invite: create invite failed: {exc}")
        return "Could not create a server invite (need Create Invite on team-queue)."

    remember_pending_ally_join(
        int(requester_discord_id),
        int(guild_id),
        int(role.id),
        team_name=str(team),
    )

    invite_url = getattr(invite, "url", None) or f"https://discord.gg/{invite.code}"
    try:
        user = await bot.fetch_user(int(requester_discord_id))
        await user.send(
            f"Your ally request for **{team}** as **{role_label}** was **accepted**.\n\n"
            f"You're not in their Discord yet — here's a **one-time** invite "
            f"(expires in 1 hour):\n{invite_url}\n\n"
            f"Joining grants the **{ALLY_ROLE_NAME}** role for `#team-queue` access. "
            "You can leave the server whenever you're done."
        )
    except Exception as exc:
        print(f"⚠️ auto-invite: DM failed: {exc}")
        return "Invite created but could not DM the ally (DMs closed?)."

    return "Sent a one-time server invite to the ally."
