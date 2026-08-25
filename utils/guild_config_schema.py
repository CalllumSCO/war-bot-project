"""Guild preference schema 

Bump ``CONFIG_SCHEMA_VERSION`` when adding a new preference option, and append
an entry to ``CONFIG_OPTIONS`` with ``introduced_in`` set to that version.

Bump ``HOW_TO_GUIDE_VERSION`` when the #how-to-use embeds change so
``/config`` → Check for updates can refresh the channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set

# Bump when adding a new toggle/preference (not channel linking).
CONFIG_SCHEMA_VERSION = 1.1

# Bump when build_how_to_use_embeds() content/layout changes.
HOW_TO_GUIDE_VERSION = 4


@dataclass(frozen=True)
class ConfigOption:
    key: str
    name: str
    description: str
    default: bool
    introduced_in: float
    kind: str = "bool"  # only bool toggles for now


CONFIG_OPTIONS: List[ConfigOption] = [
    ConfigOption(
        key="auto_invite_allies",
        name="Auto-invite allies",
        description=(
            "DM accepted allies a one-time Discord invite if they aren't in this "
            "server yet, and grant the War Bot Ally role on join."
        ),
        default=True,
        introduced_in=1,
    ),
    ConfigOption(
        key="config_update_alerts",
        name="Config update alerts",
        description=(
            "On new preference options, alert the server with a bot message."
        ),
        default=True,
        introduced_in=1.1,
    ),
]


def options_by_key() -> Dict[str, ConfigOption]:
    return {opt.key: opt for opt in CONFIG_OPTIONS}


def _as_version(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def get_config_ack_version(config: Optional[Dict[str, Any]]) -> float:
    if not config:
        return 0.0
    return _as_version(config.get("config_version_ack"))


def get_how_to_guide_version(config: Optional[Dict[str, Any]]) -> int:
    if not config:
        return 0
    try:
        return int(config.get("how_to_guide_version"))
    except (TypeError, ValueError):
        return 0


def get_config_update_alert_version(config: Optional[Dict[str, Any]]) -> float:
    """Last schema version we already posted a team-queue update alert for."""
    if not config:
        return 0.0
    return _as_version(config.get("config_update_alert_version"))


def get_reviewed_keys(config: Optional[Dict[str, Any]]) -> Set[str]:
    if not config:
        return set()
    raw = config.get("config_reviewed_keys") or []
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw}


def pending_config_options(config: Optional[Dict[str, Any]]) -> List[ConfigOption]:
    """Options introduced after the last full ack, and not yet reviewed individually."""
    ack = get_config_ack_version(config)
    reviewed = get_reviewed_keys(config)
    return [
        opt
        for opt in CONFIG_OPTIONS
        if opt.introduced_in > ack and opt.key not in reviewed
    ]


def how_to_guide_outdated(config: Optional[Dict[str, Any]]) -> bool:
    return get_how_to_guide_version(config) < HOW_TO_GUIDE_VERSION


def has_pending_updates(config: Optional[Dict[str, Any]]) -> bool:
    if not config:
        return False
    return bool(pending_config_options(config)) or how_to_guide_outdated(config)


def format_default(opt: ConfigOption) -> str:
    if opt.kind == "bool":
        return "On" if opt.default else "Off"
    return str(opt.default)


def effective_bool(config: Optional[Dict[str, Any]], opt: ConfigOption) -> bool:
    if not config or opt.key not in config:
        return bool(opt.default)
    return bool(config.get(opt.key))


def is_config_update_alerts_enabled(config: Optional[Dict[str, Any]]) -> bool:
    """Default ON — posts to #team-queue when schema is ahead of this guild."""
    opt = options_by_key().get("config_update_alerts")
    if not opt:
        return True
    return effective_bool(config, opt)


def should_alert_config_updates(config: Optional[Dict[str, Any]]) -> bool:
    """True when startup should notify #team-queue about pending config / guide updates."""
    if not config or not has_pending_updates(config):
        return False
    if not is_config_update_alerts_enabled(config):
        return False
    if get_config_update_alert_version(config) >= float(CONFIG_SCHEMA_VERSION):
        return False
    return True

def review_fields_for(
    config: Optional[Dict[str, Any]],
    keys: Iterable[str],
) -> Dict[str, Any]:
    """
    Mark option keys as reviewed. When nothing remains pending, bump
    ``config_version_ack`` to the current schema and clear the review list.
    """
    reviewed = get_reviewed_keys(config) | {str(k) for k in keys}
    trial = dict(config or {})
    trial["config_reviewed_keys"] = sorted(reviewed)
    fields: Dict[str, Any] = {"config_reviewed_keys": sorted(reviewed)}
    if not pending_config_options(trial):
        fields["config_version_ack"] = CONFIG_SCHEMA_VERSION
        fields["config_reviewed_keys"] = []
    return fields
