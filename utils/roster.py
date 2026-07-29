from typing import Any, Dict, List, Optional

ROSTER_SIZE = 5
MIN_BAGGERS = 1

SEARCH_ALLIES = "allies"
SEARCH_OPPONENTS = "opponents"

PARTY_PREPARING = "preparing"
PARTY_POSTED = "posted"
PARTY_MATCHED = "matched"
PARTY_CANCELLED = "cancelled"

BAGGER_ICON = "🛍️"  # Discord :shopping_bags:
RUNNER_ICON = "🏃"


def lineup_size(lineup: List[Dict[str, Any]]) -> int:
    return len(lineup or [])


def count_baggers(lineup: List[Dict[str, Any]]) -> int:
    return sum(
        1
        for player in lineup or []
        if player.get("bagger") or str(player.get("role") or "").lower() == "bagger"
    )


def has_minimum_bagger(lineup: List[Dict[str, Any]]) -> bool:
    return count_baggers(lineup) >= MIN_BAGGERS


def is_roster_full(lineup: List[Dict[str, Any]]) -> bool:
    return lineup_size(lineup) >= ROSTER_SIZE


def ally_slots_remaining(lineup: List[Dict[str, Any]]) -> int:
    return max(0, ROSTER_SIZE - lineup_size(lineup))


def count_runners(lineup: List[Dict[str, Any]]) -> int:
    return max(0, lineup_size(lineup) - count_baggers(lineup))


def baggers_still_needed(lineup: List[Dict[str, Any]]) -> int:
    return max(0, MIN_BAGGERS - count_baggers(lineup))


def only_baggers_can_fill(lineup: List[Dict[str, Any]]) -> bool:
    """
    True when every open slot must be a bagger — e.g. 4 runners with 1 slot left.
    Allies can still post/search before this; Available then filters to baggers only.
    """
    slots = ally_slots_remaining(lineup)
    needed = baggers_still_needed(lineup)
    return slots > 0 and needed > 0 and needed >= slots


def ally_request_role_policy(lineup: List[Dict[str, Any]]) -> Optional[str]:
    """
    What role an ally requester must use for this roster:
    - "bagger" — 4 runners / bagger-only fill
    - "runner" — roster already has a bagger (remaining slots are runners)
    - "choose" — no bagger yet and not at 4 runners (requester picks in a modal)
    - None — roster full
    """
    if is_roster_full(lineup):
        return None
    if only_baggers_can_fill(lineup):
        return "bagger"
    if has_minimum_bagger(lineup):
        return "runner"
    return "choose"


def role_allowed_for_lineup(lineup: List[Dict[str, Any]], *, bagger: bool) -> bool:
    """Whether a player of this role may join the lineup."""
    policy = ally_request_role_policy(lineup)
    if policy is None:
        return False
    if policy == "bagger":
        return bool(bagger)
    if policy == "runner":
        return not bagger
    return True


def lineup_all_baggers(lineup: List[Dict[str, Any]]) -> bool:
    size = lineup_size(lineup)
    return size > 0 and count_baggers(lineup) == size


def can_merge_as_allies(host_lineup: List[Dict[str, Any]], guest_lineup: List[Dict[str, Any]]) -> bool:
    """
    Host absorbing guest (Invite): fit in slots + bagger rules.

    If the host already has a bagger, the guest must be runners-only.
    If the host is in bagger-only fill (4 runners / 1 slot), the guest must be all baggers.
    """
    guest_size = lineup_size(guest_lineup)
    if guest_size <= 0:
        return False
    if guest_size > ally_slots_remaining(host_lineup):
        return False
    if only_baggers_can_fill(host_lineup):
        return lineup_all_baggers(guest_lineup)
    if has_minimum_bagger(host_lineup) and count_baggers(guest_lineup) > 0:
        return False
    return True


def can_join_host_as_allies(host_lineup: List[Dict[str, Any]], guest_lineup: List[Dict[str, Any]]) -> bool:
    """
    Guest requesting to join host (Request to join): same slot + bagger rules,
    with host = the Available group and guest = the viewer's group.
    """
    return can_merge_as_allies(host_lineup, guest_lineup)


def can_seek_opponents(lineup: List[Dict[str, Any]]) -> bool:
    return is_roster_full(lineup) and has_minimum_bagger(lineup)


def reconcile_search_mode(
    search_mode: str,
    lineup: List[Dict[str, Any]],
    *,
    search_time: Optional[str] = "ASAP",
    created_at: Optional[str] = None,
) -> str:
    """
    Promote to opponent search at 5/5+bagger once search time allows it;
    demote if roster drops below.
    """
    from utils.search_time import opponent_search_unlocked

    mode = search_mode or SEARCH_ALLIES
    unlocked = opponent_search_unlocked(search_time, created_at=created_at)

    if mode == SEARCH_ALLIES and can_seek_opponents(lineup) and unlocked:
        return SEARCH_OPPONENTS
    if mode == SEARCH_OPPONENTS and not can_seek_opponents(lineup):
        return SEARCH_ALLIES
    if mode == SEARCH_OPPONENTS and not unlocked:
        return SEARCH_ALLIES
    return mode


def team_queue_lobby_active(party: Dict[str, Any]) -> bool:
    """
    Team-server queue buttons stay usable while forming a roster, including after
    posting to the hub billboard in allies mode.
    """
    status = party.get("status", PARTY_PREPARING)
    lineup = party.get("lineup", [])

    if status == PARTY_PREPARING:
        return True
    if status == PARTY_POSTED and party.get("search_mode", SEARCH_ALLIES) == SEARCH_ALLIES:
        return not is_roster_full(lineup)
    return False


def resolve_search_mode(requested: Optional[str], lineup: List[Dict[str, Any]]) -> Optional[str]:
    """
    Return the effective search mode, or None if opponents was requested but roster is not ready.
    """
    mode = (requested or SEARCH_ALLIES).lower()
    if mode == SEARCH_OPPONENTS and not can_seek_opponents(lineup):
        return None
    if mode not in (SEARCH_ALLIES, SEARCH_OPPONENTS):
        return SEARCH_ALLIES
    return mode


def party_status_label(status: str) -> str:
    labels = {
        "preparing": "Forming roster",
        "posted": "In queue",
        "matched": "Matched",
        "cancelled": "Cancelled",
    }
    return labels.get(status, status)


def status_label(search_mode: str, status: str, lineup: List[Dict[str, Any]]) -> str:
    if status == "matched":
        return "Matched — awaiting gather"
    if status == "cancelled":
        return "Cancelled"
    if search_mode == SEARCH_OPPONENTS and can_seek_opponents(lineup):
        return "Looking For Opponents"
    return "Looking For Allies"


def format_lineup_entry(player: Dict[str, Any]) -> str:
    role_icon = BAGGER_ICON if player.get("bagger") or player.get("role") == "Bagger" else RUNNER_ICON
    ally_tag = " *(ally)*" if player.get("ally") else ""
    name = player.get("player", "Unknown")
    role = player.get("role", "Runner")
    return f"> {role_icon} **{name}** — {role}{ally_tag}"


def format_lineup(lineup: List[Dict[str, Any]]) -> str:
    if not lineup:
        return "> No players yet."
    return "\n".join(format_lineup_entry(player) for player in lineup)


def roster_summary(lineup: List[Dict[str, Any]]) -> str:
    size = lineup_size(lineup)
    baggers = count_baggers(lineup)
    allies = sum(1 for player in lineup if player.get("ally"))
    slots = ally_slots_remaining(lineup)
    bagger_ok = "✅" if has_minimum_bagger(lineup) else "❌"
    return (
        f"**Roster:** `{size}/{ROSTER_SIZE}` · "
        f"**Baggers:** `{baggers}` {bagger_ok} · "
        f"**Ally slots:** `{slots}` · "
        f"**Allies joined:** `{allies}`"
    )
