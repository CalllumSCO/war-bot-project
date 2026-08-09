from typing import Any, Dict, Optional, Tuple

from utils.billboard_store import delete_war, find_post_by_party_id, upsert_war
from utils.match_service import board_for_party
from utils.match_posting import create_match_post_from_party
from utils.queue_store import delete_party, get_party, upsert_party
from utils.roster import (
    SEARCH_ALLIES,
    SEARCH_OPPONENTS,
    reconcile_search_mode,
    resolve_search_mode,
    status_label,
)
from utils.search_time import format_search_time, opponent_search_unlocked

from classes.queue_party import PARTY_POSTED, PARTY_PREPARING


def filling_surface(
    party: Optional[Dict[str, Any]] = None,
    war: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Where this group is recruiting: 'web' | 'discord' | 'mixed'.

    - web: companion Available only (no Discord hub post)
    - discord: Discord hub post from a team-server party
    - mixed: web-origin group that also posted to the Discord allies billboard
    """
    if party:
        guild = 0
        try:
            guild = int(party.get("guild_id") or 0)
        except (TypeError, ValueError):
            guild = 0
        team_id = str(party.get("team_id") or "")
        web_origin = guild == 0 or team_id.startswith("web-")
        on_hub = bool(party.get("match_post_id"))
        if on_hub and web_origin:
            return "mixed"
        if on_hub:
            return "discord"
        return "web"

    if war:
        war_id = str(war.get("war_id") or "")
        if war_id.startswith("web-"):
            return "web"
        origin = 0
        try:
            origin = int(war.get("origin_guild_id") or 0)
        except (TypeError, ValueError):
            origin = 0
        if origin == 0:
            return "mixed"
        return "discord"

    return "web"


def join_party_queue(party: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Mark a party as searching on the web Available board.
    Does not post to the Discord allies billboard — use post_party_to_billboard for that.
    """
    status = party.get("status")
    if status == PARTY_POSTED:
        return party, "Already in the queue."
    if status != PARTY_PREPARING:
        return None, "This party can't join the queue right now."

    party["status"] = PARTY_POSTED
    party["search_mode"] = SEARCH_ALLIES
    party["lobby_mode"] = None  # leave friends/preview lobby
    # Keep any existing match_post_id only if a hub post still exists; otherwise clear.
    found = find_post_by_party_id(party.get("party_id"))
    if not found:
        party["match_post_id"] = None
    upsert_party(party)

    from utils.event_bus import publish_event

    publish_event(
        "queue",
        {
            "action": "join_queue",
            "party_id": party.get("party_id"),
            "board": board_for_party(party),
        },
    )
    return party, "Joined the queue."


def leave_party_queue(
    party: Dict[str, Any],
) -> Tuple[bool, Optional[str], Optional[Tuple[str, str]]]:
    """
    Stop searching: remove hub billboard post if any, revert to preparing.
    Keeps the party/group intact.

    Returns (ok, message, (board, war_id) if a hub post was removed).
    """
    if party.get("status") != PARTY_POSTED:
        return False, "This party is not in the queue.", None

    party_id = party.get("party_id")
    removed: Optional[Tuple[str, str]] = None
    found = find_post_by_party_id(party_id)
    if found:
        board, war = found
        war_id = war.get("war_id")
        delete_war(board, war_id)
        if war_id:
            removed = (board, str(war_id))

    party["status"] = PARTY_PREPARING
    party["match_post_id"] = None
    party["search_mode"] = SEARCH_ALLIES
    upsert_party(party)

    from utils.event_bus import publish_event
    from utils.party_sync import publish_party_sync

    publish_party_sync(
        "leave_queue",
        party=party,
        board=removed[0] if removed else None,
        war_id=removed[1] if removed else None,
    )
    publish_event(
        "queue",
        {
            "action": "leave_queue",
            "party_id": party.get("party_id"),
            "board": removed[0] if removed else board_for_party(party),
        },
    )
    return True, "Left the queue.", removed


def party_as_available_war(party: Dict[str, Any]) -> Dict[str, Any]:
    """Synthetic war-shaped dict for web Available (no Discord hub write)."""
    search_mode = party.get("search_mode") or SEARCH_ALLIES
    post = create_match_post_from_party(party, search_mode)
    post["war_id"] = party.get("match_post_id") or f"web-{party.get('party_id')}"
    post["status"] = "open"
    return post


def post_party_to_billboard(party: Dict[str, Any], looking_for: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    lineup = party.get("lineup", [])
    # Allies: post anytime (even 1 runner). Opponents still need 5/5 + bagger.

    # Idempotent: already on the hub.
    found = find_post_by_party_id(party.get("party_id"))
    if found:
        _board, existing = found
        if party.get("status") != PARTY_POSTED or not party.get("match_post_id"):
            party["status"] = PARTY_POSTED
            party["match_post_id"] = existing.get("war_id")
            party["search_mode"] = existing.get("search_mode") or party.get("search_mode") or SEARCH_ALLIES
            upsert_party(party)
        label = status_label(
            existing.get("search_mode") or party.get("search_mode") or "allies",
            "open",
            lineup,
        )
        return existing, f"Already posted as **{label}**."

    search_time = party.get("search_time", "ASAP")
    created_at = party.get("created_at") or party.get("last_updated")
    unlocked = opponent_search_unlocked(search_time, created_at=created_at)

    search_mode = resolve_search_mode(looking_for, lineup)
    if search_mode is None:
        return None, (
            "Looking for opponents needs a full **5/5** lineup with a bagger. "
            "Post for allies first, or finish filling the roster."
        )

    if search_mode == SEARCH_OPPONENTS and not unlocked:
        when = format_search_time(search_time)
        return None, (
            f"Opponent search opens at **{when}**. "
            "You can post for **allies** anytime before then."
        )

    search_mode = reconcile_search_mode(
        search_mode,
        lineup,
        search_time=search_time,
        created_at=created_at,
    )

    board = board_for_party(party)
    post = create_match_post_from_party(party, search_mode)
    upsert_war(board, post)

    party["status"] = PARTY_POSTED
    party["match_post_id"] = post["war_id"]
    party["search_mode"] = search_mode
    upsert_party(party)

    label = status_label(search_mode, "open", lineup)
    extra = ""
    if search_mode != SEARCH_OPPONENTS and not unlocked:
        extra = f" Opponent search opens at **{format_search_time(search_time)}**."
    return post, f"Posted as **{label}**.{extra}"


def cancel_party(party_id: str) -> bool:
    """Remove a queue party and its hub billboard post, if any."""
    party = get_party(party_id)
    if not party:
        return False

    found = find_post_by_party_id(party_id)
    lobby_channel_id = party.get("lobby_channel_id")
    lobby_message_id = party.get("lobby_message_id")
    if found:
        board, war = found
        delete_war(board, war.get("war_id"))

    delete_party(party_id)

    from utils.party_sync import publish_party_sync

    publish_party_sync(
        "cancel",
        party_id=party_id,
        board=found[0] if found else None,
        war_id=found[1].get("war_id") if found else None,
        lobby_channel_id=lobby_channel_id,
        lobby_message_id=lobby_message_id,
        party=party,
    )
    return True


def remove_player_from_party(discord_id: int, *, party_id: Optional[str] = None) -> bool:
    """
    Remove a player from their active party after joining another roster as ally.
    Cancels the party if the lineup would be empty; transfers captain if needed.
    """
    party = get_party(party_id) if party_id else None
    if not party:
        from utils.queue_store import get_active_party_for_user

        party = get_active_party_for_user(int(discord_id))
    if not party:
        return False

    lineup = list(party.get("lineup") or [])
    new_lineup = [p for p in lineup if int(p.get("discord_id") or 0) != int(discord_id)]
    if len(new_lineup) == len(lineup):
        return False

    if not new_lineup:
        return cancel_party(party["party_id"])

    party["lineup"] = new_lineup
    try:
        captain_id = int(party.get("captain_discord_id") or 0)
    except (TypeError, ValueError):
        captain_id = 0
    if captain_id == int(discord_id):
        party["captain_discord_id"] = new_lineup[0].get("discord_id")
    upsert_party(party)

    # Keep hub post in sync if this party was posted.
    found = find_post_by_party_id(party.get("party_id"))
    from utils.party_sync import publish_party_sync

    if found:
        from utils.match_posting import sync_billboard_post_from_party

        synced = sync_billboard_post_from_party(party)
        if synced:
            board, war = synced
            publish_party_sync(
                "roster_update",
                party=party,
                board=board,
                war_id=war.get("war_id"),
            )
        else:
            publish_party_sync("roster_update", party=party)
    else:
        publish_party_sync("roster_update", party=party)
    return True
