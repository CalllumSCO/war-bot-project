from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from classes.player import Player
from classes.war import War
from utils.billboard_store import find_post_by_party_id, upsert_war
from utils.roster import SEARCH_ALLIES, SEARCH_OPPONENTS, can_seek_opponents, reconcile_search_mode
from utils.search_time import opponent_search_unlocked


def lineup_from_dicts(lineup: List[Dict[str, Any]]) -> List[Player]:
    return [Player.from_dict(player) for player in lineup]


def _schedule_kwargs(source: Dict[str, Any]) -> Dict[str, Optional[str]]:
    return {
        "search_time": source.get("search_time") or source.get("start_time") or "ASAP",
        "created_at": source.get("created_at") or source.get("last_updated"),
    }


def create_match_post_from_party(party: Dict[str, Any], search_mode: str) -> Dict[str, Any]:
    """Create a hub billboard MatchPost from a team-server QueueParty."""
    lineup = lineup_from_dicts(party.get("lineup", []))
    mode = party.get("mode", "ranked")
    created_at = party.get("created_at") or party.get("last_updated")
    war = War(
        war_type=party.get("war_type", "RT"),
        team_name=party.get("team_name", "Unknown Team"),
        start_time=party.get("search_time", "ASAP"),
        search_in_advance=party.get("search_time", "ASAP") != "ASAP",
        lineup=lineup,
        search_mode=search_mode,
        status="open",
        author_discord_id=party.get("captain_discord_id"),
        origin_guild_id=party.get("guild_id"),
        party_id=party.get("party_id"),
        mode=mode,
        created_at=created_at,
    )
    war.last_updated = datetime.utcnow().isoformat()
    war.ally_count = sum(1 for player in lineup if player.ally)
    return war.to_dict()


def sync_party_lineup_from_post(party: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    party["lineup"] = post.get("lineup", [])
    party["search_mode"] = post.get("search_mode", party.get("search_mode", "allies"))
    party["mode"] = post.get("mode", party.get("mode", "ranked"))
    if post.get("status") == "matched":
        party["status"] = "matched"
    return party


def sync_billboard_post_from_party(party: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Push team-queue roster changes to the linked hub billboard post."""
    found = find_post_by_party_id(party.get("party_id"))
    if not found:
        return None

    board, war = found
    war["lineup"] = list(party.get("lineup", []))
    war["ally_count"] = sum(1 for player in war["lineup"] if player.get("ally"))
    war["last_updated"] = datetime.utcnow().isoformat()
    war["start_time"] = party.get("search_time", war.get("start_time", "ASAP"))
    if party.get("created_at") and not war.get("created_at"):
        war["created_at"] = party["created_at"]

    war["search_mode"] = reconcile_search_mode(
        war.get("search_mode", SEARCH_ALLIES),
        war["lineup"],
        **_schedule_kwargs({**war, **party}),
    )
    party["search_mode"] = war["search_mode"]

    upsert_war(board, war)
    return board, war


def promote_due_opponent_searches() -> List[Tuple[str, Dict[str, Any]]]:
    """
    Flip posted ally searches to Looking For Opponents once roster + schedule allow it.
    Returns list of (board, war) that changed.
    """
    from utils.queue_store import list_parties, upsert_party

    promoted: List[Tuple[str, Dict[str, Any]]] = []
    for party in list_parties():
        if party.get("status") != "posted":
            continue
        if party.get("search_mode") == SEARCH_OPPONENTS:
            continue
        lineup = party.get("lineup", [])
        if not can_seek_opponents(lineup):
            continue
        if not opponent_search_unlocked(
            party.get("search_time", "ASAP"),
            created_at=party.get("created_at") or party.get("last_updated"),
        ):
            continue

        # Only promote parties that already have a Discord hub post.
        found = find_post_by_party_id(party.get("party_id"))
        if not found:
            continue

        party["search_mode"] = SEARCH_OPPONENTS
        upsert_party(party)

        board, war = found
        war["lineup"] = list(lineup)
        war["ally_count"] = sum(1 for player in lineup if player.get("ally"))
        war["search_mode"] = SEARCH_OPPONENTS
        war["start_time"] = party.get("search_time", war.get("start_time", "ASAP"))
        war["last_updated"] = datetime.utcnow().isoformat()
        if party.get("created_at"):
            war["created_at"] = party["created_at"]
        upsert_war(board, war)
        promoted.append((board, war))

    return promoted
