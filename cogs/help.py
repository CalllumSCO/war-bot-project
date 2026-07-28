import interactions
from interactions import Extension, SlashContext, slash_command

from utils.colors import COLORS
from utils.config import SCOPES


def _embed(title: str, description: str) -> interactions.Embed:
    return interactions.Embed(title=title, description=description, color=COLORS["default"])


HELP_TOPICS = {
    "queue": _embed(
        "Help · /queue",
        "**Team server**\n\n"
        "• `/profile link` — link Lounge or friend code\n"
        "• `/profile view` — your ratings and recent wars\n"
        "• `/queue start` — pick track, ranked/casual, and your role\n"
        "• Casual: choose when opponent search should start (right away or a later hour)\n"
        "• Teammates join from lobby buttons\n"
        "• `/queue post` — post to the hub (needs a bagger)\n"
        "• `/queue status` / `/queue cancel`\n\n"
        "**Casual tip:** fill allies anytime; looking for opponents only goes live at your chosen time.",
    ),
    "war": _embed(
        "Help · /war",
        "**Match channel** (`war-vs-*`)\n\n"
        "• `/war complete` — report result + RXX\n"
        "• Scores pull from the WiimmFI room when possible\n"
        "• `/war scores` — manual fallback if RXX lookup fails\n"
        "• `/war confirm` — both captains confirm\n"
        "• `/war dispute` — reject a report\n"
        "• `/war cancel` / `/war approve-cancel` / `/war decline-cancel`",
    ),
    "billboard": _embed(
        "Help · Hub",
        "Hub channels: RT/CT × ranked/casual\n\n"
        "• **Request Ally** — ask to join a team (roster accepts in `#team-queue`)\n"
        "• **Request Match** — challenge a full team looking for opponents\n"
        "• `/war-view` — see your team’s hub post",
    ),
    "setup": _embed(
        "Help · Setup",
        "**Admin (once per server)**\n\n"
        "• `/team` — register this Discord as your team\n"
        "• `/setup` — create or link hub boards + team queue",
    ),
}


class HelpCommands(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @slash_command(
        name="help",
        description="War Bot guides",
        sub_cmd_name="queue",
        sub_cmd_description="Team queue commands",
        scopes=SCOPES,
    )
    async def help_queue(self, ctx: SlashContext):
        await ctx.send(embeds=HELP_TOPICS["queue"], ephemeral=True)

    @slash_command(
        name="help",
        description="War Bot guides",
        sub_cmd_name="war",
        sub_cmd_description="Match channel commands",
        scopes=SCOPES,
    )
    async def help_war(self, ctx: SlashContext):
        await ctx.send(embeds=HELP_TOPICS["war"], ephemeral=True)

    @slash_command(
        name="help",
        description="War Bot guides",
        sub_cmd_name="billboard",
        sub_cmd_description="Hub billboard flow",
        scopes=SCOPES,
    )
    async def help_billboard(self, ctx: SlashContext):
        await ctx.send(embeds=HELP_TOPICS["billboard"], ephemeral=True)

    @slash_command(
        name="help",
        description="War Bot guides",
        sub_cmd_name="setup",
        sub_cmd_description="Server setup",
        scopes=SCOPES,
    )
    async def help_setup(self, ctx: SlashContext):
        await ctx.send(embeds=HELP_TOPICS["setup"], ephemeral=True)


def setup(bot: interactions.Client):
    HelpCommands(bot)
