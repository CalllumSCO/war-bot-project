import json
import os
import interactions
from typing import Optional
from classes.player import Player
from classes.war import War
from interactions import (
    Extension,
    SlashContext,
    slash_command,
    slash_option,
    OptionType,
    SlashCommandChoice,
)
from dotenv import load_dotenv

load_dotenv(".env.local")

# devpond1412 code (^_^)
def load_billboard(path: str) -> list:
    """
    Load billboard JSON file and always return a list.
    If file is missing, invalid, or not a list, return [].
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


RT_CHANNEL_ID = os.getenv("RT_WAR_ID")
CT_CHANNEL_ID = os.getenv("CT_WAR_ID")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class CreateNewWar(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @slash_command(
        name="create-new-war",
        description="Starts a new war and posts it on the billboard. Default is RT.",
        # add scopes=[GUILD_ID] during dev if you want instant registration
    )
    @slash_option(
        name="track_type",
        description="Track type (RT or CT). If omitted, defaults to RT.",
        required=False,
        opt_type=OptionType.STRING,
        choices=[
            SlashCommandChoice(name="RT", value="RT"),
            SlashCommandChoice(name="CT", value="CT"),
        ],
    )
    async def create_new_war(
        self,
        ctx: SlashContext,
        track_type: Optional[str] = None,
    ):
        # Determine channel based on option (default RT)
        is_ct = (track_type or "RT").upper() == "CT"
        target_channel_id = CT_CHANNEL_ID if is_ct else RT_CHANNEL_ID
        track_label = "CT" if is_ct else "RT"

        # Guild (server) info
        team_name = ctx.guild.name if ctx.guild else "Unknown Server"
        user_id = ctx.author.id

        # Acknowledge to the user (ephemeral so you don’t spam the channel)
        await ctx.send(
            f"Command received in **{team_name}**.\n"
            f"Track type: **{track_label}**\n"
            f"Your user ID is `{user_id}`.",
            ephemeral=True,
        )

        # Using display name for now, will likely link with lounge in the future
        creation_player = Player(ctx.author.display_name, role="Runner", ally=False)
        creation_war = War(war_type=track_label, team_name=team_name)
        creation_war.lineup.append(creation_player)
        billboard_path = (os.path.join(BASE_DIR, 'temp', 'ct-billboard.json') if is_ct else os.path.join(BASE_DIR, 'temp', 'billboard-data', 'rt-billboard.json'))


        # Load existing data (if any)
        if os.path.exists(billboard_path):
            with open(billboard_path, "r", encoding="utf-8") as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = []
                except json.JSONDecodeError:
                    existing_data = []
        else:
            existing_data = []

        # Append the new war dict
        existing_data.append(creation_war.to_dict())

        # Write back to JSON file
        os.makedirs(os.path.dirname(billboard_path), exist_ok=True)
        with open(billboard_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)

        print(f"Added war to {billboard_path}")

        # Post to the appropriate billboard channel
        try:
            channel = await self.bot.fetch_channel(target_channel_id)
            await channel.send(
                f"New **{track_label}** war started in **{team_name}** by <@{user_id}>!"
            )
            print(f"Posted war info for {team_name} in #{getattr(channel, 'name', target_channel_id)}")
        except Exception as e:
            print(f"Error sending to target channel {target_channel_id}: {e}")


    # devpond1412 code (^_^)
    @slash_command(
        name="war-count",
        description="Show how many wars are recorded (RT/CT).",
    )
    @slash_option(
        name="track_type",
        description="Track type (RT, CT, or ALL). If omitted, shows all.",
        required=False,
        opt_type=OptionType.STRING,
        choices=[
            SlashCommandChoice(name="All", value="ALL"),
            SlashCommandChoice(name="RT", value="RT"),
            SlashCommandChoice(name="CT", value="CT"),
        ],
    )
    async def war_count(
        self,
        ctx: SlashContext,
        track_type: Optional[str] = None,
    ):
        track = (track_type or "ALL").upper()

        rt_path = os.path.join(
            BASE_DIR, "temp", "billboard-data", "rt-billboard.json"
        )
        ct_path = os.path.join(
            BASE_DIR, "temp", "ct-billboard.json"
        )

        rt_wars = load_billboard(rt_path)
        ct_wars = load_billboard(ct_path)

        rt_count = len(rt_wars)
        ct_count = len(ct_wars)
        total_count = rt_count + ct_count

        if track == "RT":
            msg = f"RT wars recorded: **{rt_count}**"
        elif track == "CT":
            msg = f"CT wars recorded: **{ct_count}**"
        else:
            msg = (
                "War counts:\n"
                f"- RT: **{rt_count}**\n"
                f"- CT: **{ct_count}**\n"
                f"- Total: **{total_count}**"
            )

        await ctx.send(msg, ephemeral=True)



def setup(bot: interactions.Client):
    CreateNewWar(bot)

