import interactions
from interactions import Extension, listen
from interactions.api.events import MessageCreate

from utils.colors import COLORS
from utils.match_message_store import append_message
from utils.match_session_store import get_session_by_channel


def _is_group_message(content: str) -> bool:
    text = (content or "").lstrip()
    lower = text.lower()
    return lower.startswith(".g ") or lower.startswith("g:")


def _strip_group_prefix(content: str) -> str:
    text = (content or "").lstrip()
    lower = text.lower()
    if lower.startswith(".g "):
        return text[3:].lstrip()
    if lower.startswith("g:"):
        return text[2:].lstrip()
    return text


class MatchRelay(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @listen(MessageCreate)
    async def relay_war_message(self, event: MessageCreate):
        message = event.message
        if not message or message.author.bot:
            return

        channel = message.channel
        if not channel:
            return
        channel_id = channel.id

        session = get_session_by_channel(channel_id)
        if not session:
            return

        if channel_id == session.get("channel_a_id"):
            peer_channel_id = session.get("channel_b_id")
            allowed_ids = set(int(x) for x in session.get("roster_a_ids", []))
        elif channel_id == session.get("channel_b_id"):
            peer_channel_id = session.get("channel_a_id")
            allowed_ids = set(int(x) for x in session.get("roster_b_ids", []))
        else:
            return

        if message.author.id not in allowed_ids:
            return

        content = (message.content or "").strip()
        if not content and not message.attachments:
            return

        author_name = message.author.display_name or message.author.username
        session_id = session.get("session_id")

        # Group chat: no peer relay (.g / g: prefix); green embed in-channel
        if _is_group_message(content):
            body = _strip_group_prefix(content) or "*(attachment)*"
            embed = interactions.Embed(
                description=body,
                color=COLORS["group_chat"],
            )
            embed.set_footer(
                text=(
                    f"{author_name} · Team-only — use g: <message> "
                    "(or .g <message>) so opponents can't see it"
                )
            )
            try:
                await channel.send(embeds=embed)
            except Exception as exc:
                print(f"❌ Failed to post group chat embed: {exc}")

            if session_id:
                try:
                    append_message(
                        session_id,
                        "group",
                        body,
                        author_discord_id=int(message.author.id),
                        author_name=author_name,
                        source="discord",
                    )
                except Exception:
                    pass

            try:
                await message.delete()
            except Exception:
                pass
            return

        # Match chat: blue embed, relay to opponent channel
        if not peer_channel_id:
            return

        body = content or "*(attachment)*"
        embed = interactions.Embed(description=body, color=COLORS["match_chat"])
        embed.set_footer(text=author_name)

        try:
            peer = await self.bot.fetch_channel(peer_channel_id)
            await peer.send(embeds=embed)
        except Exception as exc:
            print(f"❌ Failed to relay war message: {exc}")

        if session_id:
            try:
                append_message(
                    session_id,
                    "match",
                    body,
                    author_discord_id=int(message.author.id),
                    author_name=author_name,
                    source="discord",
                )
            except Exception:
                pass


def setup(bot: interactions.Client):
    MatchRelay(bot)
