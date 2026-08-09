"""Build / clear outbound invite & request cards under My Group (SendouQ-style)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from utils.ally_request_store import (
    delete_ally_request,
    list_pending_ally_for_party,
    list_pending_ally_for_requester,
)
from utils.billboard_store import find_war, find_war_across_boards, find_war_by_author
from utils.match_request_store import delete_request as delete_match_request
from utils.match_request_store import list_pending_match_for_requester_war
from utils.match_request_store import list_pending_match_for_target_war
from utils.party_invite_store import delete_party_invite, list_outbound_invites
from utils.queue_store import get_active_party_for_user, get_party


def _team_avg_rank(lineup: List[Dict[str, Any]], war_type: str) -> str:
    from utils.sr import get_player_rating, rank_for_sr

    scores: List[int] = []
    for entry in lineup or []:
        did = entry.get("discord_id")
        if did is None:
            continue
        try:
            rating = get_player_rating(
                int(did),
                war_type,
                bagger=bool(entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger"),
                role=entry.get("role"),
            )
            if rating.get("sr") is not None:
                scores.append(int(rating["sr"]))
        except Exception:
            continue
    if not scores:
        return "unranked"
    return rank_for_sr(int(round(sum(scores) / len(scores))), revealed=True)


def _exclude_ids_for_party(party: Optional[Dict[str, Any]]) -> List[str]:
    if not party:
        return []
    ids: List[str] = []
    pid = party.get("party_id")
    if pid:
        ids.append(str(pid))
    mid = party.get("match_post_id")
    if mid:
        ids.append(str(mid))
    cap = party.get("captain_discord_id")
    if cap is not None:
        ids.append(str(cap))
    return ids


def _exclude_ids_for_war(war: Optional[Dict[str, Any]]) -> List[str]:
    if not war:
        return []
    ids: List[str] = []
    wid = war.get("war_id")
    if wid:
        ids.append(str(wid))
    pid = war.get("party_id")
    if pid:
        ids.append(str(pid))
    author = war.get("author_discord_id")
    if author is not None:
        ids.append(str(author))
    return ids


def clear_outbound_pending_for_party(party_id: Optional[str]) -> None:
    """Drop all outbound invites/requests from this party (roster changed)."""
    if not party_id:
        return
    for inv in list_outbound_invites(str(party_id)):
        delete_party_invite(inv["invite_id"])
    for req in list_pending_ally_for_party(str(party_id)):
        delete_ally_request(req["request_id"])
    party = get_party(str(party_id))
    war_id = (party or {}).get("match_post_id")
    if war_id:
        for req in list_pending_match_for_requester_war(str(war_id)):
            delete_match_request(req["request_id"])


def clear_outbound_pending_for_user(discord_id: int) -> None:
    """Drop outbound ally requests sent by this user (they joined another roster)."""
    for req in list_pending_ally_for_requester(int(discord_id)):
        delete_ally_request(req["request_id"])
    party = get_active_party_for_user(int(discord_id))
    if party:
        # Also clear party-scoped invites if they're the only member / captain leaving context
        # Callers that absorbed a whole party should use clear_outbound_pending_for_party.
        pass


def build_outbound_pending(
    *,
    party: Optional[Dict[str, Any]],
    user_discord_id: int,
    enrich_lineup_entry,
) -> List[Dict[str, Any]]:
    """
    Cards shown under My Group → Invited / Requested.

    enrich_lineup_entry(entry, war_type) should match the queue router's enricher.
    """
    items: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def _add(item: Dict[str, Any]) -> None:
        rid = str(item.get("id") or "")
        if not rid or rid in seen:
            return
        seen.add(rid)
        items.append(item)

    party_id = (party or {}).get("party_id")
    war_type = (party or {}).get("war_type") or "RT"

    if party_id:
        for inv in list_outbound_invites(str(party_id)):
            target_id = inv.get("target_discord_id")
            try:
                target_id_int = int(target_id)
            except (TypeError, ValueError):
                continue
            target_party = get_active_party_for_user(target_id_int)
            players_src: List[Dict[str, Any]]
            exclude: List[str]
            if target_party:
                tw = target_party.get("war_type") or war_type
                players_src = list(target_party.get("lineup") or [])
                exclude = _exclude_ids_for_party(target_party)
            else:
                # Fall back to any open hub war authored by the target.
                war = None
                for board_guess in (
                    "rt-ranked",
                    "rt-casual",
                    "ct-ranked",
                    "ct-casual",
                ):
                    war = find_war_by_author(board_guess, target_id_int)
                    if war:
                        break
                if war:
                    tw = war.get("war_type") or war_type
                    players_src = list(war.get("lineup") or [])
                    exclude = _exclude_ids_for_war(war)
                else:
                    tw = war_type
                    players_src = [
                        {
                            "discord_id": target_id_int,
                            "player": str(target_id_int),
                            "role": "Runner",
                        }
                    ]
                    exclude = [str(target_id_int)]
            _add(
                {
                    "id": inv.get("invite_id"),
                    "kind": "invited",
                    "label": "Invited",
                    "players": [enrich_lineup_entry(p, tw) for p in players_src],
                    "exclude_ids": exclude,
                    "invite_target_discord_id": str(target_id_int),
                    "war_id": None,
                }
            )

    # Ally requests from this user (and any tied to their party).
    ally_reqs = list(list_pending_ally_for_requester(int(user_discord_id)))
    if party_id:
        for req in list_pending_ally_for_party(str(party_id)):
            if req not in ally_reqs:
                ally_reqs.append(req)

    for req in ally_reqs:
        war_id = req.get("war_id")
        found = find_war_across_boards(war_id) if war_id else None
        if not found:
            continue
        _board, war = found
        tw = war.get("war_type") or war_type
        _add(
            {
                "id": req.get("request_id"),
                "kind": "requested",
                "label": "Requested",
                "players": [enrich_lineup_entry(p, tw) for p in war.get("lineup") or []],
                "exclude_ids": _exclude_ids_for_war(war),
                "invite_target_discord_id": str(war.get("author_discord_id") or ""),
                "war_id": str(war_id),
            }
        )

    # Match requests from our hub post.
    match_post_id = (party or {}).get("match_post_id")
    if match_post_id:
        for req in list_pending_match_for_requester_war(str(match_post_id)):
            target_id = req.get("target_war_id")
            board = req.get("board")
            war = find_war(board, target_id) if board and target_id else None
            if not war:
                found = find_war_across_boards(target_id) if target_id else None
                war = found[1] if found else None
            if not war:
                continue
            tw = war.get("war_type") or war_type
            anonymous = str(war.get("mode") or "").lower() == "ranked"
            players = (
                []
                if anonymous
                else [enrich_lineup_entry(p, tw) for p in war.get("lineup") or []]
            )
            _add(
                {
                    "id": req.get("request_id"),
                    "kind": "challenged",
                    "label": "Challenged",
                    "players": players,
                    "exclude_ids": _exclude_ids_for_war(war),
                    "invite_target_discord_id": str(war.get("author_discord_id") or ""),
                    "war_id": str(war.get("war_id") or target_id),
                    "mode": war.get("mode"),
                    "anonymous": anonymous,
                    "team_avg_rank": _team_avg_rank(war.get("lineup") or [], tw),
                }
            )

    return items


def build_inbound_pending(
    *,
    party: Optional[Dict[str, Any]],
    user_discord_id: int,
    enrich_lineup_entry,
) -> List[Dict[str, Any]]:
    """Incoming party invites are separate; this adds inbound match challenges."""
    items: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    match_post_id = (party or {}).get("match_post_id")
    if not match_post_id:
        return items

    war_type = (party or {}).get("war_type") or "RT"
    for req in list_pending_match_for_target_war(str(match_post_id)):
        rid = str(req.get("request_id") or "")
        if not rid or rid in seen:
            continue
        requester_id = req.get("requester_war_id")
        board = req.get("board")
        war = find_war(board, requester_id) if board and requester_id else None
        if not war:
            found = find_war_across_boards(requester_id) if requester_id else None
            war = found[1] if found else None
        if not war:
            continue
        seen.add(rid)
        tw = war.get("war_type") or war_type
        anonymous = str(war.get("mode") or "").lower() == "ranked"
        players = (
            []
            if anonymous
            else [enrich_lineup_entry(p, tw) for p in war.get("lineup") or []]
        )
        items.append(
            {
                "id": rid,
                "kind": "challenge",
                "label": "Challenge",
                "players": players,
                "exclude_ids": _exclude_ids_for_war(war),
                "invite_target_discord_id": str(war.get("author_discord_id") or ""),
                "war_id": str(war.get("war_id") or requester_id),
                "mode": war.get("mode"),
                "anonymous": anonymous,
                "team_avg_rank": _team_avg_rank(war.get("lineup") or [], tw),
            }
        )
    return items
