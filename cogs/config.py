"""Server preference toggles + SkyHanni-style config update checks."""

from __future__ import annotations

import asyncio
import re

import interactions
from interactions import (
    ActionRow,
    Button,
    ButtonStyle,
    ComponentContext,
    Extension,
    OptionType,
    SlashCommandChoice,
    SlashContext,
    component_callback,
    listen,
    slash_command,
    slash_option,
)

from utils.colors import COLORS
from utils.config import SCOPES
from utils.discord_defer import defer_ephemeral, send_ephemeral
from utils.guild_config import (
    get_guild_config,
    is_auto_invite_allies_enabled,
    list_guild_configs,
    upsert_guild_config,
)
from utils.guild_config_schema import (
    CONFIG_SCHEMA_VERSION,
    HOW_TO_GUIDE_VERSION,
    effective_bool,
    format_default,
    get_config_ack_version,
    get_how_to_guide_version,
    has_pending_updates,
    how_to_guide_outdated,
    options_by_key,
    pending_config_options,
    review_fields_for,
    should_alert_config_updates,
)
from utils.how_to_use import refresh_how_to_use_channel
from utils.interactions_helpers import has_guild_admin


class ServerConfig(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @listen()
    async def on_startup(self):
        """Nudge #team-queue when a guild's config ack is behind the current schema."""
        await asyncio.sleep(3)
        await self._alert_outdated_guild_configs()

    async def _alert_outdated_guild_configs(self) -> None:
        notified = 0
        skipped = 0
        for config in list_guild_configs():
            try:
                if not should_alert_config_updates(config):
                    skipped += 1
                    continue

                guild_id = int(config.get("guild_id") or 0)
                channel_id = config.get("queue_channel_id")
                if not guild_id or not channel_id:
                    skipped += 1
                    continue

                pending = pending_config_options(config)
                howto_old = how_to_guide_outdated(config)
                guild_name = config.get("name") or str(guild_id)

                lines = [
                    f"**War Bot config updates available** (schema **v{CONFIG_SCHEMA_VERSION}**).",
                    "An admin should run `/config action:Check for updates` to review new "
                    "preferences (or keep defaults) and refresh `#how-to-use` if needed.",
                ]
                if pending:
                    names = ", ".join(f"**{opt.name}**" for opt in pending)
                    lines.append(f"New options: {names}")
                if howto_old:
                    lines.append(
                        f"#how-to-use guide outdated "
                        f"(**v{get_how_to_guide_version(config)}** → **v{HOW_TO_GUIDE_VERSION}**)."
                    )
                lines.append(
                    "_Turn off these alerts with_ `/config setting:Config update alerts value:Off`."
                )

                embed = interactions.Embed(
                    title="Config updates available",
                    description="\n".join(lines),
                    color=COLORS["waiting"],
                )
                embed.set_footer(text=f"War Bot · {guild_name}")

                channel = await self.bot.fetch_channel(int(channel_id))
                if channel is None:
                    skipped += 1
                    continue
                await channel.send(embeds=embed)
                upsert_guild_config(
                    guild_id,
                    guild_name,
                    config_update_alert_version=CONFIG_SCHEMA_VERSION,
                )
                notified += 1
            except Exception as exc:
                print(f"⚠️ Config update alert failed for guild {config.get('guild_id')}: {exc}")

        if notified or skipped:
            print(
                f"🔔 Config update alerts: notified {notified} guild(s), "
                f"skipped {skipped}"
            )

    @slash_command(
        name="config",
        description="View preferences, change toggles, or check for config updates.",
        scopes=SCOPES,
    )
    @slash_option(
        name="action",
        description="What to do (leave empty to view current config).",
        required=False,
        opt_type=OptionType.STRING,
        choices=[
            SlashCommandChoice(name="View config", value="view"),
            SlashCommandChoice(name="Check for updates", value="check_updates"),
            SlashCommandChoice(name="Refresh how-to-use channel", value="refresh_howto"),
        ],
    )
    @slash_option(
        name="setting",
        description="Setting to change (leave empty to view / check updates).",
        required=False,
        opt_type=OptionType.STRING,
        choices=[
            SlashCommandChoice(name="Auto-invite allies", value="auto_invite_allies"),
            SlashCommandChoice(name="Config update alerts", value="config_update_alerts"),
        ],
    )
    @slash_option(
        name="value",
        description="New value for the setting.",
        required=False,
        opt_type=OptionType.STRING,
        choices=[
            SlashCommandChoice(name="On", value="on"),
            SlashCommandChoice(name="Off", value="off"),
        ],
    )
    async def config(
        self,
        ctx: SlashContext,
        action: str | None = None,
        setting: str | None = None,
        value: str | None = None,
    ):
        # Ack within 3s before any DB / Discord I/O — avoids Unknown interaction.
        await defer_ephemeral(ctx)
        try:
            await self._config_body(ctx, action=action, setting=setting, value=value)
        except Exception as exc:
            print(f"⚠️ /config failed: {exc}")
            await send_ephemeral(
                ctx,
                embeds=interactions.Embed(
                    title="Config failed",
                    description=f"Something went wrong running `/config`.\n`{exc}`",
                    color=COLORS["error"],
                ),
            )

    async def _config_body(
        self,
        ctx: SlashContext,
        *,
        action: str | None,
        setting: str | None,
        value: str | None,
    ):
        if not ctx.guild:
            await send_ephemeral(ctx, "This command can only be used in a server.")
            return
        if not has_guild_admin(ctx):
            await send_ephemeral(
                ctx,
                "You need **Administrator** permission to manage War Bot config.",
            )
            return

        guild_id = ctx.guild.id
        guild_name = ctx.guild.name
        config = get_guild_config(guild_id)

        if not config:
            await send_ephemeral(
                ctx,
                "This server isn't set up yet. Run `/setup` first, then use `/config`.",
            )
            return

        action = (action or "view").strip().lower()

        if action == "check_updates":
            await self._send_updates_panel(ctx, guild_name, config)
            return

        if action == "refresh_howto":
            ok, note = await refresh_how_to_use_channel(ctx.guild, config=config)
            color = COLORS["default"] if ok else COLORS["error"]
            embed = interactions.Embed(
                title="How-to-use refresh" if ok else "How-to-use refresh failed",
                description=note,
                color=color,
            )
            await send_ephemeral(ctx, embeds=embed)
            return

        if setting and value:
            opt = options_by_key().get(setting)
            if not opt:
                await send_ephemeral(ctx, "Unknown setting.")
                return

            enabled = value == "on"
            fields = {
                setting: enabled,
                **review_fields_for(config, [setting]),
            }
            upsert_guild_config(guild_id, guild_name, **fields)
            config = get_guild_config(guild_id) or config

            if setting == "auto_invite_allies" and enabled:
                warn = await self._ensure_auto_invite_ready(ctx, config)
                if warn:
                    await send_ephemeral(ctx, warn)
                    return
                config = get_guild_config(guild_id) or config

            detail = {
                "auto_invite_allies": (
                    "Accepted allies who aren't in this server get a one-time DM invite."
                    if enabled
                    else "Accepted allies will not receive a Discord invite from War Bot."
                ),
                "auto_ack_new_features": (
                    "When War Bot ships new preferences, a notice will be posted in #team-queue."
                    if enabled
                    else "War Bot will not post config-update notices to #team-queue on startup."
                ),
            }.get(setting, "")

            await send_ephemeral(
                ctx,
                embeds=self._config_embed(
                    guild_name,
                    config,
                    title="Config updated",
                    description=(
                        f"**{opt.name}** is now **{'On' if enabled else 'Off'}**.\n" + detail
                    ),
                ),
            )
            return

        if setting and not value:
            await send_ephemeral(ctx, "Pick a **value** (`On` or `Off`) for that setting.")
            return

        description = (
            "Change a preference with `/config setting:… value:…`.\n"
            "Channel linking stays under `/setup`.\n"
            "After bot updates: `/config action:Check for updates`."
        )
        if has_pending_updates(config):
            description = (
                "**Config updates available** — run `/config action:Check for updates` "
                "to review new toggles (or keep defaults) and refresh `#how-to-use`.\n\n"
                + description
            )

        await send_ephemeral(
            ctx,
            embeds=self._config_embed(
                guild_name,
                config,
                title=f"Config · {guild_name}",
                description=description,
            ),
        )

    async def _send_updates_panel(self, ctx: SlashContext, guild_name: str, config: dict):
        pending = pending_config_options(config)
        howto_old = how_to_guide_outdated(config)
        guild_id = int(ctx.guild.id)

        if not pending and not howto_old:
            embed = interactions.Embed(
                title="You're up to date",
                description=(
                    f"No new preferences since schema **v{CONFIG_SCHEMA_VERSION}**.\n"
                    f"#how-to-use guide is current (**v{HOW_TO_GUIDE_VERSION}**).\n\n"
                    "You can still refresh the guide with "
                    "`/config action:Refresh how-to-use channel`."
                ),
                color=COLORS["default"],
            )
            embed.add_field(
                name="Acknowledged",
                value=(
                    f"Config ack **v{get_config_ack_version(config)}** · "
                    f"How-to **v{get_how_to_guide_version(config)}**"
                ),
                inline=False,
            )
            await send_ephemeral(ctx, embeds=embed)
            return

        lines = [
            "War Bot has new server preferences and/or guide content since this "
            "server last reviewed config — same idea as SkyHanni’s default-options prompt.",
            "",
            "Review each toggle below, or **Keep defaults** to leave them as shipped "
            "and stop this reminder.",
        ]
        embed = interactions.Embed(
            title="Config updates available",
            description="\n".join(lines),
            color=COLORS["waiting"],
        )

        for opt in pending:
            current = effective_bool(config, opt)
            current_label = "On" if current else "Off"
            if opt.key not in config:
                current_label += " (using default)"
            embed.add_field(
                name=f"New · {opt.name}",
                value=(
                    f"{opt.description}\n"
                    f"Default: **{format_default(opt)}** · Currently: **{current_label}**\n"
                    f"`/config setting:{opt.name} value:On|Off`"
                ),
                inline=False,
            )

        if howto_old:
            embed.add_field(
                name="How-to-use guide",
                value=(
                    f"Guide content updated (**v{get_how_to_guide_version(config)}** → "
                    f"**v{HOW_TO_GUIDE_VERSION}**). Refresh posts the latest embeds in "
                    f"<#{config['how_to_use_channel_id']}>."
                    if config.get("how_to_use_channel_id")
                    else (
                        f"Guide content updated (**v{HOW_TO_GUIDE_VERSION}**), but no "
                        "#how-to-use channel is linked."
                    )
                ),
                inline=False,
            )

        embed.set_footer(text=f"War Bot config updates · {guild_name}")

        buttons: list[Button] = []
        if pending and howto_old:
            keep_label = "Keep defaults + refresh how-to"
        elif howto_old and not pending:
            keep_label = "Refresh how-to & dismiss"
        else:
            keep_label = "Keep defaults"

        buttons.append(
            Button(
                style=ButtonStyle.SUCCESS,
                label=keep_label[:80],
                custom_id=f"config_keep_defaults:{guild_id}",
            ),
        )
        for opt in pending[:2]:
            short = opt.name if len(opt.name) <= 18 else opt.name.split()[0]
            buttons.append(
                Button(
                    style=ButtonStyle.PRIMARY,
                    label=f"{short}: On"[:80],
                    custom_id=f"config_set:{opt.key}:on:{guild_id}",
                )
            )
            buttons.append(
                Button(
                    style=ButtonStyle.SECONDARY,
                    label=f"{short}: Off"[:80],
                    custom_id=f"config_set:{opt.key}:off:{guild_id}",
                )
            )
        if howto_old and pending:
            buttons.append(
                Button(
                    style=ButtonStyle.SECONDARY,
                    label="Refresh how-to only",
                    custom_id=f"config_refresh_howto:{guild_id}",
                )
            )
        elif config.get("how_to_use_channel_id") and not howto_old and pending:
            buttons.append(
                Button(
                    style=ButtonStyle.SECONDARY,
                    label="Refresh how-to",
                    custom_id=f"config_refresh_howto:{guild_id}",
                )
            )

        rows = [ActionRow(*buttons[:5])]
        if len(buttons) > 5:
            rows.append(ActionRow(*buttons[5:10]))

        await send_ephemeral(ctx, embeds=embed, components=rows)

    @component_callback(re.compile(r"^config_keep_defaults:(\d+)$"))
    async def keep_defaults(self, ctx: ComponentContext):
        await defer_ephemeral(ctx)
        try:
            if not await self._guard_config_button(ctx):
                return
            guild_id = int(ctx.guild.id)
            expected = int(ctx.custom_id.split(":")[1])
            if expected != guild_id:
                await send_ephemeral(ctx, "This button is for a different server.")
                return

            config = get_guild_config(guild_id)
            if not config:
                await send_ephemeral(ctx, "Setup missing — run `/setup` first.")
                return

            notes: list[str] = []
            pending = pending_config_options(config)
            for opt in pending:
                notes.append(f"• **{opt.name}** → default **{format_default(opt)}**")

            fields = review_fields_for(config, [opt.key for opt in pending])
            upsert_guild_config(guild_id, ctx.guild.name, **fields)

            config = get_guild_config(guild_id) or config
            if how_to_guide_outdated(config):
                ok, howto_note = await refresh_how_to_use_channel(ctx.guild, config=config)
                if ok:
                    notes.append(f"• {howto_note}")
                else:
                    notes.append(f"• How-to refresh skipped: {howto_note}")

            if not notes:
                notes.append("Nothing pending — acknowledged current schema.")

            config = get_guild_config(guild_id) or config
            await send_ephemeral(
                ctx,
                embeds=self._config_embed(
                    ctx.guild.name,
                    config,
                    title="Defaults kept",
                    description=(
                        "New options left at their shipped defaults. "
                        "Change any later with `/config setting:… value:…`.\n\n"
                        + "\n".join(notes)
                    ),
                ),
            )
        except Exception as exc:
            print(f"⚠️ config_keep_defaults failed: {exc}")
            await send_ephemeral(ctx, f"Config update failed: `{exc}`")

    @component_callback(re.compile(r"^config_set:([a-z_]+):(on|off):(\d+)$"))
    async def set_option_button(self, ctx: ComponentContext):
        await defer_ephemeral(ctx)
        try:
            if not await self._guard_config_button(ctx):
                return
            parts = ctx.custom_id.split(":")
            key, value, expected = parts[1], parts[2], int(parts[3])
            guild_id = int(ctx.guild.id)
            if expected != guild_id:
                await send_ephemeral(ctx, "This button is for a different server.")
                return

            opt = options_by_key().get(key)
            if not opt:
                await send_ephemeral(ctx, "Unknown setting.")
                return

            enabled = value == "on"
            config = get_guild_config(guild_id) or {}
            fields = {
                key: enabled,
                **review_fields_for(config, [key]),
            }
            upsert_guild_config(guild_id, ctx.guild.name, **fields)
            config = get_guild_config(guild_id) or {}

            if key == "auto_invite_allies" and enabled:
                warn = await self._ensure_auto_invite_ready(ctx, config)
                if warn:
                    await send_ephemeral(ctx, warn)
                    return
                config = get_guild_config(guild_id) or config

            remaining = pending_config_options(config)
            howto_note = ""
            if not remaining and how_to_guide_outdated(config):
                ok, note = await refresh_how_to_use_channel(ctx.guild, config=config)
                howto_note = f"\n{note}" if ok else f"\nHow-to: {note}"

            await send_ephemeral(
                ctx,
                embeds=self._config_embed(
                    ctx.guild.name,
                    config,
                    title="Config updated",
                    description=(
                        f"**{opt.name}** is now **{'On' if enabled else 'Off'}**."
                        + (
                            "\nOther new options still pending — run `/config action:Check for updates` again."
                            if remaining
                            else "\nAll new preference toggles reviewed."
                        )
                        + howto_note
                    ),
                ),
            )
        except Exception as exc:
            print(f"⚠️ config_set failed: {exc}")
            await send_ephemeral(ctx, f"Config update failed: `{exc}`")

    @component_callback(re.compile(r"^config_refresh_howto:(\d+)$"))
    async def refresh_howto_button(self, ctx: ComponentContext):
        await defer_ephemeral(ctx)
        try:
            if not await self._guard_config_button(ctx):
                return
            expected = int(ctx.custom_id.split(":")[1])
            if expected != int(ctx.guild.id):
                await send_ephemeral(ctx, "This button is for a different server.")
                return

            ok, note = await refresh_how_to_use_channel(ctx.guild)
            embed = interactions.Embed(
                title="How-to-use refresh" if ok else "How-to-use refresh failed",
                description=note,
                color=COLORS["default"] if ok else COLORS["error"],
            )
            await send_ephemeral(ctx, embeds=embed)
        except Exception as exc:
            print(f"⚠️ config_refresh_howto failed: {exc}")
            await send_ephemeral(ctx, f"How-to refresh failed: `{exc}`")

    async def _guard_config_button(self, ctx: ComponentContext) -> bool:
        if not ctx.guild:
            await send_ephemeral(ctx, "Server only.")
            return False
        if not has_guild_admin(ctx):
            await send_ephemeral(ctx, "Administrator permission required.")
            return False
        return True

    async def _ensure_auto_invite_ready(self, ctx, config: dict) -> str | None:
        if not config.get("queue_channel_id"):
            return (
                "Auto-invite is **On**, but no team-queue channel is linked. "
                "Link one with `/setup` so invites can be created."
            )
        from utils.ally_server_invite import ALLY_ROLE_NAME, ensure_ally_role

        role = await ensure_ally_role(ctx.guild, config)
        if not role:
            return (
                "Auto-invite is **On**, but I couldn't create/configure the "
                f"**{ALLY_ROLE_NAME}** role (need **Manage Roles** + queue channel perms)."
            )
        return None

    def _config_embed(
        self,
        guild_name: str,
        config: dict,
        *,
        title: str,
        description: str,
    ) -> interactions.Embed:
        embed = interactions.Embed(
            title=title,
            description=description,
            color=COLORS["waiting"] if has_pending_updates(config) else COLORS["default"],
        )
        on = is_auto_invite_allies_enabled(config)
        role_id = config.get("ally_role_id")
        detail = "On (default)" if on and "auto_invite_allies" not in config else ("On" if on else "Off")
        if on and role_id:
            detail += f" · <@&{role_id}>"
        embed.add_field(name="Auto-invite allies", value=detail, inline=False)

        alerts_opt = options_by_key().get("auto_ack_new_features")
        if alerts_opt:
            alerts_on = effective_bool(config, alerts_opt)
            alerts_detail = (
                "On (default)"
                if alerts_on and "auto_ack_new_features" not in config
                else ("On" if alerts_on else "Off")
            )
            embed.add_field(name="Config update alerts", value=alerts_detail, inline=False)

        queue_id = config.get("queue_channel_id")
        embed.add_field(
            name="Team queue",
            value=f"<#{queue_id}>" if queue_id else "Not linked",
            inline=False,
        )
        howto_id = config.get("how_to_use_channel_id")
        howto_v = get_how_to_guide_version(config)
        howto_line = f"<#{howto_id}>" if howto_id else "Not linked"
        if howto_id:
            howto_line += f" · guide v{howto_v}"
            if how_to_guide_outdated(config):
                howto_line += f" (update to v{HOW_TO_GUIDE_VERSION} available)"
        embed.add_field(name="How-to-use", value=howto_line, inline=False)
        embed.add_field(
            name="Schema",
            value=(
                f"Ack **v{get_config_ack_version(config)}** / current **v{CONFIG_SCHEMA_VERSION}**"
                + (" · updates pending" if has_pending_updates(config) else "")
            ),
            inline=False,
        )
        embed.set_footer(text=f"War Bot config · {guild_name}")
        return embed


def setup(bot: interactions.Client):
    ServerConfig(bot)
