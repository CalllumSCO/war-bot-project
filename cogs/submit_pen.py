import os
import re
import aiohttp
import interactions
from io import BytesIO  # ✅ NEW
from dotenv import load_dotenv
from interactions import (
    Extension,
    SlashContext,
    slash_command,
    slash_option,
    OptionType,
    SlashCommandChoice,
    Attachment,
    Embed,
    File,
)

load_dotenv(".env.local")

# 25 MB default upload limit
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

# Allowed video/image extensions for penalties
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".gif"}


def slugify_filename(title: str, fallback: str) -> str:
    """Create a safe-ish filename from the title, falling back to original name. Removing spaces and any other chars that may
    break the application"""
    _, ext = os.path.splitext(fallback or "")
    ext = ext.lower()

    safe_title = title.strip().lower()
    safe_title = re.sub(r"[^a-z0-9]+", "_", safe_title).strip("_")

    if not safe_title:
        safe_title = "penalty"

    return f"{safe_title}{ext or ''}"


class PenSubmit(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @slash_command(
        name="submit_pen",
        description="Pings GSC Referees with a provided possible Penalty",
    )
    @slash_option(
        name="type",
        description="Match Type",
        required=True,
        opt_type=OptionType.STRING,
        choices=[
            SlashCommandChoice(name="Scrim", value="scrim"),
            SlashCommandChoice(name="Match", value="gsc_match"),
        ],
    )
    @slash_option(
        name="title",
        description="Match Header (e.g., Cy v RS - Pen on RS)",
        required=True,
        opt_type=OptionType.STRING,
    )
    @slash_option(
        name="video",
        description="Upload the GIF/Video file here",
        required=True,
        opt_type=OptionType.ATTACHMENT,
    )
    async def submitpen(
        self,
        ctx: SlashContext,
        type: str,
        title: str,
        video: Attachment,
    ):
        await ctx.defer(ephemeral=True)

        # Channel / role IDs from env
        spec_channel_id = (
            int(os.getenv("SCRIM_PEN_CHANNEL"))
            if type == "scrim"
            else int(os.getenv("GSC_PEN_CHANNEL"))
        )
        ref_role_id = os.getenv("REF_ID")

        if not spec_channel_id:
            return await ctx.send(
                "Config error: SCRIM_PEN_CHANNEL / GSC_PEN_CHANNEL is not set.",
                ephemeral=True,
            )

        if not ref_role_id:
            return await ctx.send(
                "Config error: REF_ID (referee role ID) is not set.",
                ephemeral=True,
            )

        channel = await self.bot.fetch_channel(spec_channel_id)
        if not channel:
            return await ctx.send(
                "Unable to locate the referee channel.", ephemeral=True
            )

        embed = Embed(
            title=title,
            description=f"Submitted by: {ctx.author.mention}",
            color=0x00FF00,
        )

        try:
            # Size check if present
            size = getattr(video, "size", None)
            if size is not None and size > MAX_FILE_SIZE_BYTES:
                mb = round(size / (1024 * 1024), 2)
                limit_mb = round(MAX_FILE_SIZE_BYTES / (1024 * 1024), 2)
                return await ctx.send(
                    f"That file is too large ({mb} MB).\n"
                    f"The current limit is {limit_mb} MB. "
                    "Please compress/trim the video or upload a smaller file.",
                    ephemeral=True,
                )

            # Extension check
            filename = video.filename or "penalty.mp4" # Backup file name if not safe
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            if ALLOWED_EXTENSIONS and ext not in ALLOWED_EXTENSIONS:
                allowed_pretty = ", ".join(sorted(ALLOWED_EXTENSIONS))
                return await ctx.send(
                    f"Unsupported file type `{ext or 'unknown'}`.\n"
                    f"Allowed types: {allowed_pretty}",
                    ephemeral=True,
                )

            # Get Discord CDN URL for the attachment
            file_url = getattr(video, "url", None)
            if not file_url:
                return await ctx.send(
                    "Couldn't resolve the attachment URL from Discord.",
                    ephemeral=True,
                )

            # Download from CDN with aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as resp:
                    if resp.status != 200:
                        return await ctx.send(
                            f"Failed to download the attachment from Discord (HTTP {resp.status}).",
                            ephemeral=True,
                        )
                    file_bytes = await resp.read()

            auto_name = slugify_filename(title, filename)

            penalty_file = File(
                BytesIO(file_bytes),  # Used to make the file bytes act like an object (needed for sending)
                file_name=auto_name,
            )

            await channel.send(
                content=f"<@&{ref_role_id}>",
                embeds=[embed],
                files=[penalty_file],
            )

            await ctx.send("Penalty submitted successfully!", ephemeral=True)

        except Exception as e:
            print("SubmitPen Error:", repr(e))
            await ctx.send(
                "Something went wrong when submitting your penalty!",
                ephemeral=True,
            )


def setup(bot: interactions.Client):
    PenSubmit(bot)
