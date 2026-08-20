from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.billboard_store import delete_war, find_post_by_party_id, upsert_war
from utils.match_service import board_for_party
from utils.match_posting import create_match_post_from_party
from utils.queue_store import delete_party, get_party, list_parties, upsert_party
from utils.roster import (
    SEARCH_ALLIES,
    SEARCH_OPPONENTS,
    can_seek_opponents,
    reconcile_search_mode,
    resolve_search_mode,
    status_label,
)
from utils.search_time import format_search_time, opponent_search_unlocked

from classes.queue_party import PARTY_POSTED, PARTY_PREPARING, PARTY_MATCHED

QUEUE_IDLE_HIDE_AFTER = timedelta(hours=1)
QUEUE_HIDDEN_SOLO_EXPIRE_AFTER = timedelta(hours=1)


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def is_queue_hidden(party: Optional[Dict[str, Any]]) -> bool:
    return bool(party and party.get("queue_hidden"))


def has_discord_hub_post(party: Optional[Dict[str, Any]]) -> bool:
    """True when the party is (or was meant to be) on the Discord allies/opponents hub."""
    if not party:
        return False
    if party.get("match_post_id"):
        return True
    return find_post_by_party_id(party.get("party_id")) is not None


def is_idle_hide_exempt(party: Optional[Dict[str, Any]]) -> bool:
    """
    Discord team-server parties (and anyone currently on the hub/allies board)
    stay public so web users can still join — never soft-hide them for idle.
    """
    if not party:
        return False
    if has_discord_hub_post(party):
        return True
    try:
        if int(party.get("guild_id") or 0) != 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def ensure_roster_activity_stamp(party: Dict[str, Any]) -> Dict[str, Any]:
    """Backfill last_roster_change_at for older parties (do not overwrite)."""
    if party.get("last_roster_change_at"):
        return party
    party["last_roster_change_at"] = (
        party.get("created_at") or party.get("last_updated") or _utcnow_iso()
    )
    return party


def touch_roster_change(party: Dict[str, Any]) -> Dict[str, Any]:
    """Call whenever lineup membership changes (join/leave/kick/merge)."""
    party["last_roster_change_at"] = _utcnow_iso()
    # Joining/leaving un-hides so they become visible again (hub restore is separate).
    if party.get("queue_hidden"):
        party["queue_hidden"] = False
        party["hidden_at"] = None
    return party


def _parse_iso(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1]
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _restore_queue_surfaces(party: Dict[str, Any]) -> Dict[str, Any]:
    """Recreate Discord hub post for a posted, visible party if missing."""
    if party.get("status") != PARTY_POSTED or party.get("queue_hidden"):
        return party
    if find_post_by_party_id(party.get("party_id")):
        return party

    search_mode = party.get("search_mode") or SEARCH_ALLIES
    if search_mode == SEARCH_OPPONENTS and can_seek_opponents(party.get("lineup", [])):
        post, err = ensure_opponent_hub_post(party)
        if err and not post:
            print(f"⚠️ restore_queue_surfaces hub restore failed: {err}")
    else:
        guild = 0
        try:
            guild = int(party.get("guild_id") or 0)
        except (TypeError, ValueError):
            guild = 0
        if guild:
            post_party_to_billboard(party, SEARCH_ALLIES)

    return get_party(party.get("party_id")) or party


def _publish_unhide_queue(party: Dict[str, Any]) -> None:
    from utils.event_bus import publish_event
    from utils.party_sync import publish_party_sync

    publish_party_sync("unhide_queue", party=party, board=board_for_party(party))
    publish_event(
        "queue",
        {
            "action": "unhide_queue",
            "party_id": party.get("party_id"),
            "board": board_for_party(party),
        },
    )


def finalize_roster_change(
    party: Dict[str, Any],
    *,
    was_hidden: bool,
) -> Dict[str, Any]:
    """
    After lineup membership change + upsert: recreate hub if the party was soft-hidden.
    """
    if not was_hidden or party.get("status") != PARTY_POSTED:
        return party
    party = _restore_queue_surfaces(party)
    _publish_unhide_queue(party)
    return party


def hide_party_from_queue(party: Dict[str, Any]) -> Dict[str, Any]:
    """Soft-hide: stay posted for self, invisible on public boards."""
    if party.get("status") != PARTY_POSTED:
        return party
    if party.get("queue_hidden"):
        return party
    # Discord hub / allies-board parties stay public so web users can still join.
    if is_idle_hide_exempt(party):
        return party

    found = find_post_by_party_id(party.get("party_id"))
    removed_board = None
    removed_war_id = None
    if found:
        board, war = found
        removed_board = board
        removed_war_id = war.get("war_id")
        delete_war(board, removed_war_id)

    party["queue_hidden"] = True
    party["hidden_at"] = _utcnow_iso()
    party["match_post_id"] = None
    party["status"] = PARTY_POSTED
    upsert_party(party)

    from utils.event_bus import publish_event
    from utils.party_sync import publish_party_sync

    publish_party_sync(
        "hide_queue",
        party=party,
        board=removed_board,
        war_id=removed_war_id,
    )
    publish_event(
        "queue",
        {
            "action": "hide_queue",
            "party_id": party.get("party_id"),
            "board": removed_board or board_for_party(party),
        },
    )
    return party


def unhide_party_queue(party: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Restore visibility after idle hide (captain action)."""
    if party.get("status") != PARTY_POSTED:
        return None, "This party is not in the queue."
    if not party.get("queue_hidden"):
        return party, "Already visible in the queue."

    party["queue_hidden"] = False
    party["hidden_at"] = None
    party["last_roster_change_at"] = _utcnow_iso()
    upsert_party(party)

    party = _restore_queue_surfaces(party)
    _publish_unhide_queue(party)
    return party, "You're visible in the queue again."


def sweep_idle_queue_parties() -> List[str]:
    """
    Hide posted *web-only* parties idle (no roster change) for 1h.
    Parties with a Discord hub / allies billboard post are never idle-hidden.
    Hard-remove solo parties hidden for another 1h. Multi-player stay hidden.
    """
    notes: List[str] = []
    now = datetime.utcnow()
    for party in list_parties():
        if party.get("status") != PARTY_POSTED:
            continue
        party = ensure_roster_activity_stamp(party)
        party_id = party.get("party_id")
        lineup = party.get("lineup") or []
        solo = len(lineup) <= 1

        # Never idle-hide Discord allies/hub posters (web can still join them).
        if is_idle_hide_exempt(party):
            if party.get("queue_hidden"):
                # Recover accidental hides for Discord/hub parties.
                unhide_party_queue(party)
                notes.append(f"unhide_hub_party:{party_id}")
            continue

        if party.get("queue_hidden"):
            if not solo:
                continue
            hidden_at = _parse_iso(party.get("hidden_at"))
            if not hidden_at:
                continue
            if now - hidden_at >= QUEUE_HIDDEN_SOLO_EXPIRE_AFTER:
                if cancel_party(str(party_id)):
                    notes.append(f"expired_solo_hidden:{party_id}")
            continue

        last = _parse_iso(party.get("last_roster_change_at"))
        if not last:
            continue
        if now - last >= QUEUE_IDLE_HIDE_AFTER:
            hide_party_from_queue(party)
            notes.append(f"hidden_idle:{party_id}")
    return notes


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


def recover_stale_matched_party(party: Dict[str, Any]) -> Dict[str, Any]:
    """Re-open a party left in matched state when accept failed mid-flight."""
    if party.get("status") != PARTY_MATCHED:
        return party

    from utils.match_session_store import get_session_by_war_id, get_session_for_user

    for entry in party.get("lineup", []) or []:
        raw = entry.get("discord_id")
        if raw is None:
            continue
        try:
            if get_session_for_user(int(raw)):
                return party
        except (TypeError, ValueError):
            continue

    war_id = party.get("match_post_id")
    if war_id and get_session_by_war_id(str(war_id)):
        return party

    found = find_post_by_party_id(party.get("party_id"))
    if found:
        board, war = found
        # Accept succeeded — never put a matched hub post back in queue.
        if war.get("status") == "matched":
            return party
        if war.get("status") == "open":
            party["status"] = PARTY_POSTED
            party["search_mode"] = war.get("search_mode") or party.get("search_mode") or SEARCH_ALLIES
            upsert_party(party)
            return party
    party["status"] = PARTY_PREPARING
    upsert_party(party)
    return party


def join_party_queue(party: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Mark a party as searching on the web Available board.
    Does not post to the Discord allies billboard — use post_party_to_billboard for that.
    """
    status = party.get("status")
    if status == PARTY_POSTED and not party.get("queue_hidden"):
        return party, "Already in the queue."
    if status == PARTY_POSTED and party.get("queue_hidden"):
        return unhide_party_queue(party)
    if status != PARTY_PREPARING:
        return None, "This party can't join the queue right now."

    party["status"] = PARTY_POSTED
    party["search_mode"] = SEARCH_ALLIES
    party["lobby_mode"] = None  # leave friends/preview lobby
    party["queue_hidden"] = False
    party["hidden_at"] = None
    party = ensure_roster_activity_stamp(party)
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


def ensure_opponent_hub_post(party: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Keep a web/Discord party in queue, and make sure they have an open LFO hub post
    so web Challenge can target Discord opponent-search posts.
    Does not require leave/rejoin.
    """
    if party.get("status") != PARTY_POSTED:
        return None, "Join the queue before challenging an opponent."
    lineup = party.get("lineup", [])
    if not can_seek_opponents(lineup):
        return None, "Your roster must be 5/5 with at least 1 bagger to request a match."

    found = find_post_by_party_id(party.get("party_id"))
    if found:
        _board, war = found
        if war.get("status") != "open":
            return None, "Your war post is no longer open."
        if war.get("search_mode") != SEARCH_OPPONENTS:
            war["search_mode"] = SEARCH_OPPONENTS
            upsert_war(_board, war)
            from utils.party_sync import publish_party_sync

            publish_party_sync(
                "roster_update",
                party=party,
                board=_board,
                war_id=war.get("war_id"),
            )
        party["match_post_id"] = war.get("war_id")
        party["search_mode"] = SEARCH_OPPONENTS
        party["status"] = PARTY_POSTED
        upsert_party(party)
        return war, None

    post, message = post_party_to_billboard(party, SEARCH_OPPONENTS)
    if not post:
        return None, message or "Could not prepare your opponent-search post."
    from utils.party_sync import publish_party_sync

    publish_party_sync(
        "post",
        party=get_party(party.get("party_id")) or party,
        board=board_for_party(party),
        war_id=post.get("war_id"),
    )
    return post, None


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
    party["queue_hidden"] = False
    party["hidden_at"] = None
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
    party["queue_hidden"] = False
    party["hidden_at"] = None
    party = ensure_roster_activity_stamp(party)
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
    was_hidden = bool(party.get("queue_hidden"))
    party = touch_roster_change(party)
    try:
        captain_id = int(party.get("captain_discord_id") or 0)
    except (TypeError, ValueError):
        captain_id = 0
    if captain_id == int(discord_id):
        party["captain_discord_id"] = new_lineup[0].get("discord_id")
    upsert_party(party)
    party = finalize_roster_change(party, was_hidden=was_hidden)

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
