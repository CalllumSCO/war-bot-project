"""Post / refresh the #how-to-use guide for a guild."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from utils.embeds import build_how_to_use_embeds
from utils.guild_config import get_guild_config, upsert_guild_config
from utils.guild_config_schema import HOW_TO_GUIDE_VERSION


_HOW_TO_TITLES = {
    "How to use War Bot",
    "Match chat · blue embeds",
    "Group chat · green embeds",
    "Allies & auto-invite",
}


def _message_looks_like_how_to(message) -> bool:
    embeds = getattr(message, "embeds", None) or []
    for embed in embeds:
        title = (getattr(embed, "title", None) or "").strip()
        if title in _HOW_TO_TITLES or title.startswith("How to use War Bot"):
            return True
    return False


async def _delete_message_quiet(channel, message_id: int) -> bool:
    """Delete a message by id without a prior fetch (avoids noisy GET 404s)."""
    mid = int(message_id)
    # Prefer direct delete when the library exposes it.
    delete_direct = getattr(channel, "delete_message", None)
    if callable(delete_direct):
        try:
            await delete_direct(mid)
            return True
        except Exception:
            return False

    try:
        msg = await channel.fetch_message(mid)
        await msg.delete()
        return True
    except Exception:
        return False


async def refresh_how_to_use_channel(
    guild,
    *,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Clear prior how-to posts (best-effort) and post the current guide.

    Returns (ok, human message). Never raises to callers.
    """
    try:
        guild_id = int(guild.id)
        config = config or get_guild_config(guild_id)
        if not config:
            return False, "This server isn't set up yet."

        channel_id = config.get("how_to_use_channel_id")
        if not channel_id:
            return (
                False,
                "No **#how-to-use** channel linked. Use `/setup` → Create category, "
                "or link one manually later.",
            )

        try:
            channel = await guild.fetch_channel(int(channel_id))
        except Exception as exc:
            return False, f"Couldn't open the how-to channel (`{channel_id}`): {exc}"
        if channel is None:
            return False, f"Couldn't find the how-to channel (`{channel_id}`)."

        deleted = 0
        stored_ids = list(config.get("how_to_message_ids") or [])
        for mid in stored_ids:
            try:
                if await _delete_message_quiet(channel, int(mid)):
                    deleted += 1
            except Exception:
                pass

        try:
            messages = await channel.fetch_messages(limit=30)
            for message in messages:
                author = getattr(message, "author", None)
                me = getattr(guild, "me", None)
                if author and me and author.id == me.id and _message_looks_like_how_to(message):
                    try:
                        await message.delete()
                        deleted += 1
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            posted = await channel.send(embeds=build_how_to_use_embeds())
        except Exception as exc:
            # Clear stale ids so the next attempt doesn't keep hammering missing messages.
            try:
                upsert_guild_config(
                    guild_id,
                    guild.name,
                    how_to_message_ids=[],
                )
            except Exception:
                pass
            return False, f"Couldn't post the how-to guide: {exc}"

        upsert_guild_config(
            guild_id,
            guild.name,
            how_to_use_channel_id=int(channel_id),
            how_to_message_ids=[int(posted.id)],
            how_to_guide_version=HOW_TO_GUIDE_VERSION,
        )
        note = f"Updated <#{channel_id}>"
        if deleted:
            note += f" (removed {deleted} old guide message{'s' if deleted != 1 else ''})"
        return True, note
    except Exception as exc:
        print(f"⚠️ refresh_how_to_use_channel crashed: {exc}")
        return False, f"How-to refresh failed unexpectedly: {exc}"
