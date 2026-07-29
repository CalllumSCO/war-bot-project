"""Grant Ally role when an auto-invited ally joins the team server."""

from __future__ import annotations

import interactions
from interactions import Extension, listen
from interactions.api.events import MemberAdd

from utils.pending_ally_joins import pop_pending_ally_join


class AllyJoin(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @listen(MemberAdd)
    async def on_member_add(self, event: MemberAdd):
        member = event.member
        guild = event.guild or getattr(member, "guild", None)
        if not member or not guild:
            return

        pending = pop_pending_ally_join(int(member.id), int(guild.id))
        if not pending:
            return

        role_id = pending.get("ally_role_id")
        if not role_id:
            return
        try:
            role = await guild.fetch_role(int(role_id))
            await member.add_role(role, reason="War Bot auto-invite ally joined")
        except Exception as exc:
            print(f"⚠️ AllyJoin: could not assign role {role_id} to {member.id}: {exc}")
            return

        team = pending.get("team_name") or guild.name
        try:
            await member.send(
                f"Welcome — you've been given **War Bot Ally** access to **{team}**'s `#team-queue`. "
                "You can leave the server when you're done queueing."
            )
        except Exception:
            pass


def setup(bot: interactions.Client):
    AllyJoin(bot)
