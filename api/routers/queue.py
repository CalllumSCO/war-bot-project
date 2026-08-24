"""My Group + Available boards + invites/requests — the web queue flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from api.auth.deps import CurrentUser, get_current_user, require_linked_fc
from api.services.profile_fields import (
    get_extended_profile_fields,
    get_extended_profile_fields_many,
)
from classes.player import Player
from classes.queue_party import MODE_RANKED, PARTY_POSTED, PARTY_PREPARING, QueueParty
from domain.match import (
    create_ally_request,
    create_party_invite,
    delete_ally_request,
    delete_match_request,
    delete_party_invite,
    finalize_match,
    get_ally_request,
    get_match_request,
    get_party_invite,
    list_inbound_invites,
    list_outbound_invites,
    pending_ally_for_war_and_user,
    start_match_request,
    upsert_ally_request,
    upsert_match_request,
    upsert_party_invite,
)
from domain.queue import (
    cancel_party,
    filling_surface,
    finalize_roster_change,
    get_active_party_for_user,
    get_party,
    get_party_by_invite,
    ensure_opponent_hub_post,
    is_queue_hidden,
    join_party_queue,
    leave_party_queue,
    list_parties,
    party_as_available_war,
    post_party_to_billboard,
    recover_stale_matched_party,
    remove_player_from_party,
    sync_party_lineup_from_post,
    touch_roster_change,
    unhide_party_queue,
    upsert_party,
)
from utils.match_service import board_for_party
from domain.ratings import get_player_rating
from domain.roster import (
    ROSTER_SIZE,
    SEARCH_ALLIES,
    SEARCH_OPPONENTS,
    ally_request_role_policy,
    can_join_host_as_allies,
    can_merge_as_allies,
    can_seek_opponents,
    is_roster_full,
    only_baggers_can_fill,
    reconcile_search_mode,
    role_allowed_for_lineup,
)
from utils.billboard_store import (
    find_war,
    find_war_across_boards,
    find_war_by_author,
    load_wars,
    upsert_war,
)
from utils.boards import ALL_BOARD_KEYS
from utils.lineup_lock import find_blocking_lineup, lineup_lock_message

router = APIRouter(tags=["queue"])


def _player_in_lineup(lineup: list[dict[str, Any]], discord_id: int) -> bool:
    return any(_ids_equal(entry.get("discord_id"), discord_id) for entry in lineup)


def _ids_equal(left: Any, right: Any) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right and left is not None


def _is_captain(party: dict[str, Any], discord_id: int) -> bool:
    return _ids_equal(party.get("captain_discord_id"), discord_id)


def _enrich_lineup_entry(
    entry: dict[str, Any],
    war_type: str,
    *,
    profiles: dict[int, dict[str, Any]] | None = None,
    ratings: dict[int, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Attach display-only avatar / SR / rank for the web UI (not persisted)."""
    out = dict(entry)
    discord_id = entry.get("discord_id")
    if discord_id is None:
        return out
    # Always string — JS JSON.parse corrupts snowflake ints (>2^53).
    try:
        did = int(discord_id)
        out["discord_id"] = str(did)
    except (TypeError, ValueError):
        out["discord_id"] = str(discord_id)
        return out

    try:
        extended = (profiles or {}).get(did)
        if extended is None:
            extended = get_extended_profile_fields(did)
        if extended.get("discord_avatar_url"):
            out["avatar"] = extended["discord_avatar_url"]
        if extended.get("display_name"):
            out["player"] = extended["display_name"]
        if extended.get("chat_name_color") and extended.get("supporter"):
            out["name_color"] = extended["chat_name_color"]
    except Exception:
        pass

    try:
        is_bagger = bool(entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger")
        role_key = "bagger" if is_bagger else "runner"
        rating = None
        if ratings is not None and did in ratings:
            rating = ratings[did].get(role_key)
        if rating is None:
            from utils.sr import get_player_rating

            rating = get_player_rating(
                did,
                war_type,
                bagger=is_bagger,
                role=entry.get("role"),
            )
        revealed = bool((rating or {}).get("revealed"))
        out["rank"] = (rating or {}).get("rank") if revealed else "unranked"
        sr = (rating or {}).get("sr")
        out["sr"] = int(sr) if revealed and sr is not None else None
    except Exception:
        out.setdefault("rank", "unranked")
    return out


def _batch_enrich_lineup(lineup: list[dict[str, Any]], war_type: str) -> list[dict[str, Any]]:
    """Enrich a lineup with two DB round-trips total (profiles + ratings)."""
    ids: list[int] = []
    for entry in lineup or []:
        raw = entry.get("discord_id")
        if raw is None:
            continue
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    profiles = get_extended_profile_fields_many(ids) if ids else {}
    ratings: dict[int, dict[str, dict[str, Any]]] = {}
    if ids:
        from utils.sr import get_player_ratings_for_ids

        ratings = get_player_ratings_for_ids(ids, war_type)
    return [
        _enrich_lineup_entry(entry, war_type, profiles=profiles, ratings=ratings)
        for entry in (lineup or [])
    ]


def _enrich_party(party: dict[str, Any] | None) -> dict[str, Any] | None:
    if not party:
        return None
    war_type = party.get("war_type") or "RT"
    enriched = dict(party)
    lineup = list(party.get("lineup", []) or [])
    enriched["lineup"] = _batch_enrich_lineup(lineup, war_type)
    enriched["filling_surface"] = filling_surface(party=party)
    enriched["lobby_mode"] = party.get("lobby_mode")
    enriched["queue_hidden"] = bool(party.get("queue_hidden"))
    enriched["hidden_at"] = party.get("hidden_at")
    avg_sr = _lineup_avg_sr(enriched["lineup"], war_type, prefer_enriched=True)
    enriched["team_avg_sr"] = avg_sr
    if avg_sr is not None:
        from utils.sr import rank_for_sr

        enriched["team_avg_rank"] = rank_for_sr(int(avg_sr), revealed=True)
    else:
        enriched["team_avg_rank"] = "unranked"
    from utils.lineup_sr import enrich_with_lineup_team

    enriched = enrich_with_lineup_team(enriched, lineup, war_type)
    for key in ("captain_discord_id", "guild_id"):
        if enriched.get(key) is not None:
            try:
                enriched[key] = str(int(enriched[key]))
            except (TypeError, ValueError):
                enriched[key] = str(enriched[key])
    return enriched


def _enrich_inbound_invite(invite: dict[str, Any]) -> dict[str, Any]:
    """Attach the inviting party's roster so the Invitations column shows names."""
    out = dict(invite)
    for key in ("from_discord_id", "target_discord_id"):
        if out.get(key) is not None:
            try:
                out[key] = str(int(out[key]))
            except (TypeError, ValueError):
                out[key] = str(out[key])
    party = get_party(str(invite.get("party_id") or ""))
    war_type = (party or {}).get("war_type") or "RT"
    lineup = list((party or {}).get("lineup") or [])
    if not lineup:
        from_id = invite.get("from_discord_id")
        if from_id is not None:
            lineup = [
                {
                    "discord_id": str(from_id),
                    "player": str(from_id),
                    "role": "Runner",
                    "bagger": False,
                }
            ]
    out["from_lineup"] = _batch_enrich_lineup(lineup, war_type)
    return out


def _redact_ranked_opponent(war: dict[str, Any], team_avg_sr: int | None) -> dict[str, Any]:
    """Ranked matchmaking: hide identities — keep war id + team avg rank only."""
    from utils.sr import rank_for_sr

    out = dict(war)
    out["lineup"] = []
    out["team_name"] = None
    out["author_discord_id"] = None
    out["team_avg_sr"] = team_avg_sr
    out["team_avg_rank"] = (
        rank_for_sr(int(team_avg_sr), revealed=True) if team_avg_sr is not None else "unranked"
    )
    out["anonymous"] = True
    return out


def _redact_for_queue_spy(war: dict[str, Any]) -> dict[str, Any]:
    """Supporter preview: keep ranks only — no names, avatars, or Discord ids."""
    out = dict(war)
    redacted = []
    for i, entry in enumerate(war.get("lineup") or []):
        redacted.append(
            {
                "discord_id": f"spy-{i}",
                "player": "?",
                "role": entry.get("role"),
                "bagger": entry.get("bagger"),
                "rank": entry.get("rank") or "unranked",
                "sr": None,
                "avatar": None,
                "avatarUrl": None,
                "name_color": None,
            }
        )
    out["lineup"] = redacted
    out["team_name"] = None
    out["author_discord_id"] = None
    return out


def _apply_casual_lineup_card_rank(
    enriched: dict[str, Any],
    lineup: list[dict[str, Any]],
    war_type: str,
) -> dict[str, Any]:
    """Casual boards: prefer revealed lineup team SR over live average snapshot."""
    from utils.lineup_sr import lineup_display_fields
    from utils.sr import rank_for_sr

    out = dict(enriched)
    fields = lineup_display_fields(lineup, war_type)
    if fields.get("lineup_revealed") and fields.get("lineup_team_sr") is not None:
        out["team_avg_sr"] = fields["lineup_team_sr"]
        out["team_avg_rank"] = fields["lineup_team_rank"]
        out["lineup_seeded"] = True
    elif out.get("team_avg_sr") is not None:
        out["team_avg_rank"] = rank_for_sr(int(out["team_avg_sr"]), revealed=True)
    for key, value in fields.items():
        if key.startswith("lineup_") or key == "lineup_id":
            out[key] = value
    return out


def _enrich_war(war: dict[str, Any]) -> dict[str, Any]:
    war_type = war.get("war_type") or "RT"
    enriched = dict(war)
    lineup = list(war.get("lineup", []) or [])
    enriched["lineup"] = _batch_enrich_lineup(lineup, war_type)
    # Prefer party metadata when linked — more accurate for web vs mixed.
    party = get_party(war["party_id"]) if war.get("party_id") else None
    enriched["filling_surface"] = (
        filling_surface(party=party) if party else filling_surface(war=war)
    )
    from utils.lineup_sr import enrich_with_lineup_team

    enriched = enrich_with_lineup_team(enriched, lineup, war_type)
    for key in ("author_discord_id", "origin_guild_id", "guild_id"):
        if enriched.get(key) is not None:
            try:
                enriched[key] = str(int(enriched[key]))
            except (TypeError, ValueError):
                enriched[key] = str(enriched[key])
    return enriched


def _touch_war(war: dict[str, Any]) -> dict[str, Any]:
    war["last_updated"] = datetime.now(timezone.utc).isoformat()
    war["ally_count"] = sum(1 for player in war.get("lineup", []) if player.get("ally"))
    return war


def _resync_billboard_from_party(party: dict[str, Any]) -> dict[str, Any]:
    """Push a party's roster onto its hub billboard post, if it has one."""
    if party.get("status") == PARTY_PREPARING:
        from utils.party_sync import publish_party_sync

        # Lobby-only refresh (preparing parties still show in #team-queue).
        publish_party_sync("roster_update", party=party)
        return party

    from utils.match_posting import sync_billboard_post_from_party
    from utils.party_sync import publish_party_sync

    found = sync_billboard_post_from_party(party)
    if found:
        board, war = found
        upsert_party(party)
        publish_party_sync(
            "roster_update",
            party=party,
            board=board,
            war_id=war.get("war_id"),
        )
    else:
        publish_party_sync("roster_update", party=party)
    return party


def _create_web_solo_party(
    user: CurrentUser,
    *,
    war_type: str,
    mode: str,
    role_name: str,
    is_bagger: bool,
    search_time: str = "ASAP",
    team_name: str | None = None,
) -> dict[str, Any]:
    lineup = [
        Player(
            player=user.display_name,
            role=role_name,
            ally=False,
            bagger=is_bagger,
            discord_id=user.discord_id,
        )
    ]
    party = QueueParty(
        team_id=f"web-{user.discord_id}",
        guild_id=0,
        team_name=team_name or f"{user.display_name}'s Team",
        war_type=war_type,
        captain_discord_id=user.discord_id,
        search_time=search_time or "ASAP",
        mode=mode or MODE_RANKED,
        lineup=lineup,
    )
    data = party.to_dict()
    upsert_party(data)
    return data


def _validate_board(board: str) -> str:
    if board not in ALL_BOARD_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown board '{board}'. Expected one of {ALL_BOARD_KEYS}.",
        )
    return board


def _find_request(request_id: str) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    ally = get_ally_request(request_id)
    if ally:
        return "ally", ally
    match = get_match_request(request_id)
    if match:
        return "match", match
    invite = get_party_invite(request_id)
    if invite:
        return "invite", invite
    return None, None


# ---------------------------------------------------------------------------
# My Group
# ---------------------------------------------------------------------------


class PartyCreate(BaseModel):
    war_type: str = Field(..., description="'RT' or 'CT'")
    mode: str = Field(default=MODE_RANKED, description="'ranked' or 'casual'")
    role: str = Field(default="Runner", description="'Runner' or 'Bagger'")
    search_time: str = Field(default="ASAP")
    team_name: str | None = None
    # friends = lobby only (no Available). preview = supporter queue spy.
    lobby_mode: str | None = Field(default=None, description="'friends' | 'preview' | null")
    join_queue: bool = Field(
        default=False,
        description="If true, immediately join the web Available queue after creating.",
    )


@router.get("/me/group")
def get_my_group(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    party = get_active_party_for_user(user.discord_id)
    if party:
        party = recover_stale_matched_party(party)
    inbound = [_enrich_inbound_invite(inv) for inv in list_inbound_invites(user.discord_id)]
    outbound = list_outbound_invites(party["party_id"]) if party else []
    from utils.pending_outbound import build_inbound_pending, build_outbound_pending

    outbound_pending = build_outbound_pending(
        party=party,
        user_discord_id=user.discord_id,
        enrich_lineup_entry=_enrich_lineup_entry,
    )
    inbound_pending = build_inbound_pending(
        party=party,
        user_discord_id=user.discord_id,
        enrich_lineup_entry=_enrich_lineup_entry,
    )
    from utils.match_session_store import get_session_for_user

    active_session = get_session_for_user(user.discord_id)
    active_match = None
    if active_session and active_session.get("session_id"):
        active_match = {
            "session_id": active_session.get("session_id"),
            "team_a_name": active_session.get("team_a_name"),
            "team_b_name": active_session.get("team_b_name"),
        }
    return {
        "party": _enrich_party(party),
        "inbound_invites": inbound,
        "outbound_invites": outbound,
        "outbound_pending": outbound_pending,
        "inbound_pending": inbound_pending,
        "active_match": active_match,
    }


@router.post("/parties", status_code=status.HTTP_201_CREATED)
def create_party(
    body: PartyCreate,
    user: CurrentUser = Depends(require_linked_fc),
) -> dict[str, Any]:
    if get_active_party_for_user(user.discord_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have an active party.")

    war_type = body.war_type.strip().upper()
    if war_type not in ("RT", "CT"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "war_type must be 'RT' or 'CT'.")

    lobby_mode = (body.lobby_mode or "").strip().lower() or None
    if lobby_mode and lobby_mode not in ("friends", "preview"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "lobby_mode must be 'friends' or 'preview'.")
    if lobby_mode == "preview":
        from api.services.profile_fields import is_supporter

        if not is_supporter(user.discord_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Queue preview is a supporter perk.",
            )
    if body.join_queue and lobby_mode:
        lobby_mode = None

    is_bagger = body.role.strip().lower() == "bagger"
    role_name = "Bagger" if is_bagger else "Runner"
    lineup = [
        Player(
            player=user.display_name,
            role=role_name,
            ally=False,
            bagger=is_bagger,
            discord_id=user.discord_id,
        )
    ]

    party = QueueParty(
        team_id=f"web-{user.discord_id}",
        guild_id=0,
        team_name=body.team_name or f"{user.display_name}'s Team",
        war_type=war_type,
        captain_discord_id=user.discord_id,
        search_time=body.search_time,
        mode=body.mode,
        lineup=lineup,
    )
    data = party.to_dict()
    data["lobby_mode"] = lobby_mode

    if body.join_queue:
        updated, message = join_party_queue(data)
        if not updated:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, message or "Could not join the queue.")
        data = updated
    else:
        upsert_party(data)

    return _enrich_party(get_party(data["party_id"]) or data)


class PartyUpdate(BaseModel):
    war_type: str | None = Field(default=None, description="'RT' or 'CT'")
    role: str | None = Field(default=None, description="Captain's own role: Runner/Bagger")
    search_time: str | None = None


@router.patch("/parties/{party_id}")
def update_party(
    party_id: str,
    body: PartyUpdate,
    user: CurrentUser = Depends(require_linked_fc),
) -> dict[str, Any]:
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    if party.get("captain_discord_id") != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the captain can update the party.")
    if party.get("status") not in (PARTY_PREPARING, PARTY_POSTED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This party can no longer be edited.")

    if body.war_type is not None:
        war_type = body.war_type.strip().upper()
        if war_type not in ("RT", "CT"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "war_type must be 'RT' or 'CT'.")
        party["war_type"] = war_type

    if body.search_time is not None:
        party["search_time"] = body.search_time.strip() or "ASAP"

    if body.role is not None:
        is_bagger = body.role.strip().lower() == "bagger"
        role_name = "Bagger" if is_bagger else "Runner"
        lineup = list(party.get("lineup", []))
        for entry in lineup:
            if entry.get("discord_id") == user.discord_id:
                entry["role"] = role_name
                entry["bagger"] = is_bagger
                break
        party["lineup"] = lineup

    upsert_party(party)
    _resync_billboard_from_party(party)
    return _enrich_party(get_party(party_id))


@router.post("/parties/{party_id}/leave")
def leave_party(
    party_id: str,
    recreate_solo: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Leave a roster.

    - recreate_solo=False (default): fully leave — no new My Group (red Leave).
    - recreate_solo=True: open a fresh solo lobby (Leave roster).
    """
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    try:
        is_captain = int(party.get("captain_discord_id")) == int(user.discord_id)
    except (TypeError, ValueError):
        is_captain = party.get("captain_discord_id") == user.discord_id
    if is_captain:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Captains must cancel the party (DELETE) instead of leaving.",
        )

    lineup = party.get("lineup", [])
    me_entry = next(
        (
            p
            for p in lineup
            if int(p.get("discord_id") or 0) == int(user.discord_id)
        ),
        None,
    )
    if me_entry is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are not in this party.")

    war_type = str(party.get("war_type") or "RT").upper()
    mode = party.get("mode") or MODE_RANKED
    search_time = party.get("search_time") or "ASAP"
    is_bagger = bool(
        me_entry.get("bagger") or str(me_entry.get("role") or "").lower() == "bagger"
    )
    role_name = "Bagger" if is_bagger else "Runner"

    new_lineup = [
        p
        for p in lineup
        if int(p.get("discord_id") or 0) != int(user.discord_id)
    ]

    if not new_lineup:
        cancel_party(party_id)
    else:
        party["lineup"] = new_lineup
        was_hidden = bool(party.get("queue_hidden"))
        party = touch_roster_change(party)
        upsert_party(party)
        party = finalize_roster_change(party, was_hidden=was_hidden)
        _resync_billboard_from_party(party)

    # Clear any leftover party still tied to this user (stale solo / desynced captain).
    for _ in range(8):
        leftover = get_active_party_for_user(user.discord_id)
        if not leftover:
            break
        leftover_id = str(leftover.get("party_id") or "")
        leftover_lineup = list(leftover.get("lineup") or [])
        others = [
            p
            for p in leftover_lineup
            if int(p.get("discord_id") or 0) != int(user.discord_id)
        ]
        if others:
            leftover["lineup"] = others
            try:
                if int(leftover.get("captain_discord_id") or 0) == int(user.discord_id):
                    leftover["captain_discord_id"] = others[0].get("discord_id")
            except (TypeError, ValueError):
                pass
            upsert_party(leftover)
            _resync_billboard_from_party(leftover)
            continue
        cancel_party(leftover_id)

    if not recreate_solo:
        return {"left": True, "party": None}

    solo = _create_web_solo_party(
        user,
        war_type=war_type if war_type in ("RT", "CT") else "RT",
        mode=mode,
        role_name=role_name,
        is_bagger=is_bagger,
        search_time=search_time,
    )
    return {"left": True, "party": _enrich_party(solo)}


@router.post("/parties/{party_id}/join-queue")
def join_queue_endpoint(
    party_id: str, user: CurrentUser = Depends(require_linked_fc)
) -> dict[str, Any]:
    """Join the web Available queue (does not post to Discord allies billboard)."""
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    if not _is_captain(party, user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the captain can join the queue.")

    party = recover_stale_matched_party(party)
    updated, message = join_party_queue(party)
    if not updated:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message or "Could not join the queue.")

    return {
        "party": _enrich_party(get_party(party_id)),
        "message": message,
    }


@router.post("/parties/{party_id}/leave-queue")
def leave_queue_endpoint(
    party_id: str, user: CurrentUser = Depends(require_linked_fc)
) -> dict[str, Any]:
    """Leave the web queue and remove any Discord allies billboard post. Keeps the group."""
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    if not _is_captain(party, user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the captain can leave the queue.")

    ok, message, _removed = leave_party_queue(party)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message or "Could not leave the queue.")

    return {
        "party": _enrich_party(get_party(party_id)),
        "message": message,
    }


@router.post("/parties/{party_id}/unhide-queue")
def unhide_queue_endpoint(
    party_id: str, user: CurrentUser = Depends(require_linked_fc)
) -> dict[str, Any]:
    """Restore visibility after idle soft-hide."""
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    if not _is_captain(party, user.discord_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the captain can restore queue visibility."
        )

    updated, message = unhide_party_queue(party)
    if not updated:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, message or "Could not restore queue visibility."
        )
    return {"party": _enrich_party(get_party(party_id)), "message": message}


@router.post("/parties/{party_id}/post")
def post_party(party_id: str, user: CurrentUser = Depends(require_linked_fc)) -> dict[str, Any]:
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    if not _is_captain(party, user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the captain can post to the hub.")

    try:
        post, message = post_party_to_billboard(party)
    except Exception as exc:
        print(f"❌ post_party_to_billboard failed for {party_id}: {exc}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Could not post to the hub: {exc}",
        ) from exc

    if not post:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message or "Could not post to the hub.")

    from utils.party_sync import publish_party_sync

    updated = get_party(party_id) or party
    publish_party_sync(
        "post",
        party=updated,
        board=board_for_party(updated),
        war_id=post.get("war_id"),
    )

    return {
        "party": _enrich_party(updated),
        "post": post,
        "message": message,
    }


@router.delete("/parties/{party_id}")
def delete_party_endpoint(
    party_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    if party.get("captain_discord_id") != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the captain can cancel the party.")

    deleted = cancel_party(party_id)
    return {"deleted": deleted}


@router.get("/parties/invite/{invite_code}")
def get_party_by_invite_code(
    invite_code: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    party = get_party_by_invite(invite_code)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found or no longer active.")
    return party


class PartyInviteCreate(BaseModel):
    # Accept digit string from the web client — JS Number() corrupts snowflakes.
    target_discord_id: int

    @field_validator("target_discord_id", mode="before")
    @classmethod
    def _snowflake(cls, value: object) -> int:
        return int(str(value).strip())


@router.post("/parties/{party_id}/invites", status_code=status.HTTP_201_CREATED)
def invite_to_party(
    party_id: str,
    body: PartyInviteCreate,
    user: CurrentUser = Depends(require_linked_fc),
) -> dict[str, Any]:
    party = get_party(party_id)
    if not party:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Party not found.")
    if not _is_captain(party, user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the captain can send invites.")
    if is_roster_full(party.get("lineup", [])):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This party's roster is already full (5/5).")
    if _player_in_lineup(party.get("lineup", []), body.target_discord_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That player is already in this party.")

    invite = create_party_invite(party_id, user.discord_id, body.target_discord_id)
    from utils.event_bus import publish_event

    publish_event(
        "queue",
        {
            "action": "invite_created",
            "invite_id": invite.get("invite_id"),
            "party_id": party_id,
            "from_discord_id": user.discord_id,
            "target_discord_id": int(body.target_discord_id),
        },
    )
    return invite


# ---------------------------------------------------------------------------
# Available boards (allies / opponents)
# ---------------------------------------------------------------------------


@router.get("/available/allies")
def available_allies(
    board: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    board = _validate_board(board)
    from utils.boards import parse_board_key

    war_type, board_mode = parse_board_key(board)
    casual_board = str(board_mode or "").lower() != "ranked"
    viewer = get_active_party_for_user(user.discord_id)
    viewer_lineup = (viewer or {}).get("lineup", []) if viewer else []
    viewer_party_id = (viewer or {}).get("party_id")
    viewer_posted = bool(viewer and viewer.get("status") == PARTY_POSTED)

    from api.services.profile_fields import is_supporter

    queue_spy = bool(
        viewer
        and viewer.get("status") == PARTY_PREPARING
        and viewer.get("lobby_mode") == "preview"
        and is_supporter(user.discord_id)
    )

    # Friends lobby (or no party): cannot peek at Available. Supporter preview can.
    if not viewer_posted and not queue_spy:
        return []

    results = []
    seen_party_ids: set[str] = set()

    def _include(war: dict[str, Any]) -> None:
        if war.get("status") != "open" or war.get("search_mode") != SEARCH_ALLIES:
            return
        if war.get("author_discord_id") == user.discord_id:
            return
        party_id = war.get("party_id")
        if viewer_party_id and party_id and party_id == viewer_party_id:
            return
        if party_id and party_id in seen_party_ids:
            return
        if party_id and is_queue_hidden(get_party(str(party_id))):
            return
        other = war.get("lineup", [])
        if viewer_lineup and not queue_spy:
            war_id = str(war.get("war_id") or "")
            # Discord hub posts → Request to join (they are host). Web parties → Invite (you are host).
            join_them = bool(war_id) and not war_id.startswith("web-")
            ok = (
                can_join_host_as_allies(other, viewer_lineup)
                if join_them
                else can_merge_as_allies(viewer_lineup, other)
            )
            if not ok:
                return
        if party_id:
            seen_party_ids.add(party_id)
        enriched = _enrich_war(war)
        if queue_spy:
            enriched = _redact_for_queue_spy(enriched)
        elif casual_board:
            enriched = _apply_casual_lineup_card_rank(
                enriched,
                war.get("lineup") or [],
                war.get("war_type") or war_type,
            )
        results.append(enriched)

    for war in load_wars(board):
        _include(war)

    # Web-queued parties that have not (yet) been posted to the Discord allies billboard.
    for party in list_parties():
        if party.get("status") != PARTY_POSTED:
            continue
        if is_queue_hidden(party):
            continue
        if (party.get("search_mode") or SEARCH_ALLIES) != SEARCH_ALLIES:
            continue
        if board_for_party(party) != board:
            continue
        party_id = party.get("party_id")
        if party_id and party_id in seen_party_ids:
            continue
        _include(party_as_available_war(party))

    return results


def _entry_display_sr(
    entry: dict[str, Any],
    war_type: str,
    *,
    prefer_enriched: bool = False,
) -> int:
    """Prefer TrueSkill display SR; fall back to legacy player MMR."""
    if prefer_enriched and entry.get("sr") is not None:
        try:
            return int(entry["sr"])
        except (TypeError, ValueError):
            pass
    from utils.sr import get_player_rating

    discord_id = entry.get("discord_id")
    if discord_id is None:
        return 0
    try:
        rating = get_player_rating(
            int(discord_id),
            war_type,
            bagger=bool(entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger"),
            role=entry.get("role"),
        )
        sr = rating.get("sr")
        if sr is not None:
            return int(sr)
    except Exception:
        pass
    try:
        from utils.player_store import get_player

        player = get_player(int(discord_id))
        return int(player.get("mmr") or 0)
    except Exception:
        return 0


def _lineup_avg_sr(
    lineup: list[dict[str, Any]],
    war_type: str,
    *,
    prefer_enriched: bool = False,
) -> int | None:
    scores = [
        _entry_display_sr(entry, war_type, prefer_enriched=prefer_enriched)
        for entry in lineup or []
        if entry.get("discord_id")
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores))


@router.get("/available/opponents")
def available_opponents(
    board: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    board = _validate_board(board)
    from utils.boards import parse_board_key
    from utils.search_time import opponent_search_unlocked
    from api.services.profile_fields import is_supporter

    war_type, mode = parse_board_key(board)
    viewer = get_active_party_for_user(user.discord_id)
    queue_spy = bool(
        viewer
        and viewer.get("status") == PARTY_PREPARING
        and viewer.get("lobby_mode") == "preview"
        and is_supporter(user.discord_id)
    )
    ranked_board = str(mode or "").lower() == "ranked"

    your_avg: int | None = None
    viewer_war = find_war_by_author(board, user.discord_id)
    if (
        viewer_war
        and viewer_war.get("status") == "open"
        and viewer_war.get("search_mode") == SEARCH_OPPONENTS
    ):
        your_avg = _lineup_avg_sr(viewer_war.get("lineup", []), war_type)

    # Live matchmaking: only full teams looking for opponents.
    # Queue spy (supporter preview): peek at opponent-searching posts even before you're queued.
    if not queue_spy:
        if not viewer or viewer.get("status") != PARTY_POSTED:
            return []
        if not can_seek_opponents(viewer.get("lineup", [])):
            return []

    results = []
    viewer_party_id = (viewer or {}).get("party_id")
    for war in load_wars(board):
        if war.get("status") != "open" or war.get("search_mode") != SEARCH_OPPONENTS:
            continue
        if _ids_equal(war.get("author_discord_id"), user.discord_id):
            continue
        if viewer_party_id and war.get("party_id") == viewer_party_id:
            continue
        party_id = war.get("party_id")
        if party_id and is_queue_hidden(get_party(str(party_id))):
            continue
        lineup = war.get("lineup", [])
        if not can_seek_opponents(lineup):
            continue
        unlocked = opponent_search_unlocked(
            war.get("start_time", "ASAP"),
            created_at=war.get("created_at") or war.get("last_updated"),
        )
        if not unlocked and not queue_spy:
            continue
        team_avg_sr = _lineup_avg_sr(lineup, war_type)
        enriched = _enrich_war(war)
        enriched["team_avg_sr"] = team_avg_sr
        enriched["delta_vs_you"] = (
            (team_avg_sr - your_avg) if team_avg_sr is not None and your_avg is not None else None
        )
        if queue_spy:
            enriched = _redact_for_queue_spy(enriched)
            enriched["team_avg_sr"] = team_avg_sr
            enriched["delta_vs_you"] = None
        elif ranked_board:
            enriched = _redact_ranked_opponent(enriched, team_avg_sr)
            enriched["delta_vs_you"] = None
        else:
            enriched = _apply_casual_lineup_card_rank(enriched, lineup, war_type)
            if not enriched.get("lineup_seeded"):
                from utils.sr import rank_for_sr

                enriched["team_avg_rank"] = (
                    rank_for_sr(int(team_avg_sr), revealed=True)
                    if team_avg_sr is not None
                    else "unranked"
                )
            enriched["anonymous"] = False
        results.append(enriched)
    return results


# ---------------------------------------------------------------------------
# Hub requests (ally / match)
# ---------------------------------------------------------------------------


class AllyRequestCreate(BaseModel):
    role: str = "Runner"


@router.post("/hub/{war_id}/ally-request", status_code=status.HTTP_201_CREATED)
def create_ally_request_endpoint(
    war_id: str,
    body: AllyRequestCreate,
    user: CurrentUser = Depends(require_linked_fc),
) -> dict[str, Any]:
    found = find_war_across_boards(war_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "War post not found.")
    board, war = found

    if war.get("status") != "open" or war.get("search_mode") != SEARCH_ALLIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This war is not accepting allies right now.")

    lineup = war.get("lineup", [])
    if is_roster_full(lineup):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This roster is already full (5/5).")
    if _player_in_lineup(lineup, user.discord_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are already on this roster.")
    if war.get("author_discord_id") == user.discord_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot join your own war as an ally.")

    viewer_party = get_active_party_for_user(user.discord_id)
    viewer_party_id = viewer_party.get("party_id") if viewer_party else None

    block = find_blocking_lineup(
        user.discord_id,
        exclude_war_id=war_id,
        exclude_party_id=viewer_party_id,
    )
    if block:
        raise HTTPException(status.HTTP_409_CONFLICT, lineup_lock_message(block))

    if pending_ally_for_war_and_user(war_id, user.discord_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a pending ally request for this war.")

    policy = ally_request_role_policy(lineup)
    if policy is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This roster is already full (5/5).")

    # Prefer the requester's current party role when policy allows a choice.
    party_role_bagger = False
    if viewer_party:
        for entry in viewer_party.get("lineup", []):
            if entry.get("discord_id") == user.discord_id:
                party_role_bagger = bool(
                    entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger"
                )
                break

    requested_bagger = body.role.strip().lower() == "bagger"
    if policy == "bagger":
        is_bagger = True
    elif policy == "runner":
        is_bagger = False
    else:
        is_bagger = party_role_bagger if viewer_party else requested_bagger

    if not role_allowed_for_lineup(lineup, bagger=is_bagger):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That role isn't available for this roster right now.",
        )
    role_name = "Bagger" if is_bagger else "Runner"
    request = create_ally_request(
        board,
        war_id,
        user.discord_id,
        user.display_name,
        role_name,
        requester_party_id=viewer_party_id,
    )

    from utils.event_bus import publish_event

    publish_event(
        "ally_request",
        {
            "request_id": request["request_id"],
            "board": board,
            "war_id": war_id,
            "origin_guild_id": war.get("origin_guild_id"),
            "captain_discord_id": war.get("author_discord_id"),
            "team_name": war.get("team_name"),
            "requester_discord_id": user.discord_id,
            "requester_name": user.display_name,
            "requester_party_id": viewer_party_id,
            "role": role_name,
        },
    )
    return request


@router.post("/hub/{war_id}/match-request", status_code=status.HTTP_201_CREATED)
def create_match_request_endpoint(
    war_id: str,
    user: CurrentUser = Depends(require_linked_fc),
) -> dict[str, Any]:
    found = find_war_across_boards(war_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "War post not found.")
    board, target_war = found

    if target_war.get("status") != "open":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This war is no longer available.")
    if target_war.get("search_mode") != SEARCH_OPPONENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This team is still looking for allies, not opponents.")
    if not can_seek_opponents(target_war.get("lineup", [])):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This team does not have a confirmed 5/5 lineup yet.")
    if _ids_equal(target_war.get("author_discord_id"), user.discord_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot request your own war.")

    party = get_active_party_for_user(user.discord_id)
    requester_war = None
    if (
        party
        and _is_captain(party, user.discord_id)
        and party.get("status") == PARTY_POSTED
        and can_seek_opponents(party.get("lineup", []))
    ):
        requester_war, ensure_error = ensure_opponent_hub_post(party)
        if ensure_error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, ensure_error)
    if not requester_war:
        requester_war = find_war_by_author(board, user.discord_id)
    if not requester_war:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You need your own open war post in Looking For Opponents mode before requesting.",
        )
    if requester_war.get("search_mode") != SEARCH_OPPONENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Switch your war to Looking For Opponents first.")
    if not can_seek_opponents(requester_war.get("lineup", [])):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Your roster must be 5/5 with at least 1 bagger to request a match.",
        )

    # Web challenges should show the captain's companion identity, not a stale Discord team name.
    web_label = f"{user.display_name}'s Team"
    requester_war["team_name"] = web_label
    upsert_war(board, requester_war)
    if party:
        party["team_name"] = web_label
        upsert_party(party)

    request, error = start_match_request(board, target_war["war_id"], requester_war["war_id"])
    if error:
        raise HTTPException(status.HTTP_409_CONFLICT, error)

    from utils.event_bus import publish_event

    publish_event(
        "match_request",
        {
            "request_id": request["request_id"],
            "board": board,
            "target_war_id": target_war.get("war_id"),
            "requester_war_id": requester_war.get("war_id"),
            "origin_guild_id": target_war.get("origin_guild_id"),
            "captain_discord_id": target_war.get("author_discord_id"),
            "team_name": target_war.get("team_name"),
        },
    )
    return request


# ---------------------------------------------------------------------------
# Generic accept/deny for ally requests, match requests, and party invites
# ---------------------------------------------------------------------------


def _accept_ally_request(request: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    if request.get("status") != "pending":
        raise HTTPException(status.HTTP_410_GONE, "This ally request is no longer active.")

    found = find_war_across_boards(request["war_id"])
    if not found:
        delete_ally_request(request["request_id"])
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The war post no longer exists.")
    board, war = found
    lineup = war.get("lineup", [])

    if not _player_in_lineup(lineup, user.discord_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only current roster members can accept ally requests.")
    if war.get("status") != "open" or war.get("search_mode") != SEARCH_ALLIES:
        delete_ally_request(request["request_id"])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This war is not accepting allies anymore.")
    if is_roster_full(lineup):
        delete_ally_request(request["request_id"])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roster is already full (5/5).")

    requester_id = request["requester_discord_id"]
    if _player_in_lineup(lineup, requester_id):
        delete_ally_request(request["request_id"])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That player is already on the roster.")

    requester_party_id = request.get("requester_party_id")
    block = find_blocking_lineup(
        requester_id,
        exclude_war_id=war["war_id"],
        exclude_party_id=requester_party_id,
    )
    if block:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot accept — {lineup_lock_message(block)}")

    role_name = request.get("role", "Runner")
    is_bagger = role_name == "Bagger" or str(role_name).lower() == "bagger"
    if not role_allowed_for_lineup(lineup, bagger=is_bagger):
        policy = ally_request_role_policy(lineup)
        if policy == "bagger":
            detail = "This roster only has a bagger slot left — can't accept a runner."
        elif policy == "runner":
            detail = "This roster already has a bagger — can't accept another bagger."
        else:
            detail = "That role isn't available for this roster right now."
        delete_ally_request(request["request_id"])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail)

    # Free the requester from their web/party lineup before joining this war.
    remove_player_from_party(int(requester_id), party_id=requester_party_id)

    lineup.append(
        Player(
            player=request.get("requester_name") or str(requester_id),
            role="Bagger" if is_bagger else "Runner",
            ally=True,
            bagger=is_bagger,
            discord_id=requester_id,
        ).to_dict()
    )
    war["lineup"] = lineup
    war["search_mode"] = reconcile_search_mode(
        war.get("search_mode", SEARCH_ALLIES),
        lineup,
        search_time=war.get("start_time", "ASAP"),
        created_at=war.get("created_at") or war.get("last_updated"),
    )
    war = _touch_war(war)
    upsert_war(board, war)

    party_id = war.get("party_id")
    if party_id:
        party = get_party(party_id)
        if party:
            synced = sync_party_lineup_from_post(party, war)
            was_hidden = bool(synced.get("queue_hidden"))
            touch_roster_change(synced)
            upsert_party(synced)
            finalize_roster_change(synced, was_hidden=was_hidden)

    request["status"] = "accepted"
    upsert_ally_request(request)
    delete_ally_request(request["request_id"])

    from utils.pending_outbound import (
        clear_outbound_pending_for_party,
        clear_outbound_pending_for_user,
    )

    clear_outbound_pending_for_user(int(requester_id))
    if party_id:
        clear_outbound_pending_for_party(str(party_id))

    return {"kind": "ally", "war": war}


def _deny_ally_request(request: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    if request.get("status") != "pending":
        raise HTTPException(status.HTTP_410_GONE, "This ally request is no longer active.")

    try:
        is_requester = int(request.get("requester_discord_id")) == int(user.discord_id)
    except (TypeError, ValueError):
        is_requester = False

    if not is_requester:
        found = find_war_across_boards(request["war_id"])
        if found:
            _, war = found
            if not _player_in_lineup(war.get("lineup", []), user.discord_id):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Only the requester or current roster members can cancel ally requests.",
                )
        else:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "That war post no longer exists.")

    delete_ally_request(request["request_id"])
    return {"kind": "ally", "status": "denied"}


def _accept_match_request(request: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    if request.get("status") != "pending":
        raise HTTPException(status.HTTP_410_GONE, "This match request is no longer active.")

    board = request["board"]
    target_war = find_war(board, request["target_war_id"])
    requester_war = find_war(board, request["requester_war_id"])
    if not target_war or not requester_war:
        delete_match_request(request["request_id"])
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One of the war posts no longer exists.")

    if target_war.get("author_discord_id") != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the defending team's captain can accept this match.")

    target_war, requester_war = finalize_match(board, target_war, requester_war)

    request["status"] = "accepted"
    upsert_match_request(request)
    delete_match_request(request["request_id"])

    return {
        "kind": "match",
        "target_war": target_war,
        "requester_war": requester_war,
        "note": "The bot will create your private war-comm channels shortly.",
    }


def _deny_match_request(request: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    if request.get("status") != "pending":
        raise HTTPException(status.HTTP_410_GONE, "This match request is no longer active.")

    board = request["board"]
    target_war = find_war(board, request["target_war_id"])
    requester_war = find_war(board, request.get("requester_war_id"))

    is_target_captain = bool(
        target_war and target_war.get("author_discord_id") == user.discord_id
    )
    is_requester_captain = bool(
        requester_war and requester_war.get("author_discord_id") == user.discord_id
    )
    if not is_target_captain and not is_requester_captain:
        if not target_war:
            delete_match_request(request["request_id"])
            raise HTTPException(status.HTTP_404_NOT_FOUND, "War post not found.")
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only either team's captain can cancel this match request.",
        )

    if not target_war and not is_requester_captain:
        delete_match_request(request["request_id"])
        raise HTTPException(status.HTTP_404_NOT_FOUND, "War post not found.")

    request["status"] = "denied"
    upsert_match_request(request)
    delete_match_request(request["request_id"])
    return {"kind": "match", "status": "denied"}


def _accept_party_invite(invite: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    if invite.get("status") != "pending":
        raise HTTPException(status.HTTP_410_GONE, "This invite is no longer active.")
    if int(invite.get("target_discord_id")) != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This invite is not for you.")

    party_a = get_party(invite["party_id"])  # the inviting party
    if not party_a:
        delete_party_invite(invite["invite_id"])
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That party no longer exists.")
    if party_a.get("status") not in (PARTY_PREPARING, PARTY_POSTED):
        delete_party_invite(invite["invite_id"])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That party is no longer accepting members.")

    party_b = get_active_party_for_user(user.discord_id)
    if party_b and party_b.get("party_id") == party_a.get("party_id"):
        delete_party_invite(invite["invite_id"])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are already in this party.")

    block = find_blocking_lineup(
        user.discord_id,
        exclude_party_id=party_b.get("party_id") if party_b else None,
    )
    if block:
        raise HTTPException(status.HTTP_409_CONFLICT, lineup_lock_message(block))

    if not party_b:
        lineup = party_a.get("lineup", [])
        if is_roster_full(lineup):
            delete_party_invite(invite["invite_id"])
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That party's roster is already full (5/5).")
        # Solo join without an active party — default runner unless host needs a bagger.
        is_bagger = only_baggers_can_fill(lineup)
        if not role_allowed_for_lineup(lineup, bagger=is_bagger):
            delete_party_invite(invite["invite_id"])
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "That party only has a bagger slot left.",
            )
        role_name = "Bagger" if is_bagger else "Runner"
        lineup.append(
            Player(
                player=user.display_name,
                role=role_name,
                ally=False,
                bagger=is_bagger,
                discord_id=user.discord_id,
            ).to_dict()
        )
        party_a["lineup"] = lineup
        was_hidden = bool(party_a.get("queue_hidden"))
        touch_roster_change(party_a)
        upsert_party(party_a)
        finalize_roster_change(party_a, was_hidden=was_hidden)
        _resync_billboard_from_party(party_a)

        from utils.pending_outbound import (
            clear_outbound_pending_for_party,
            clear_outbound_pending_for_user,
        )

        clear_outbound_pending_for_party(party_a.get("party_id"))
        clear_outbound_pending_for_user(user.discord_id)

        invite["status"] = "accepted"
        upsert_party_invite(invite)
        delete_party_invite(invite["invite_id"])
        from utils.event_bus import publish_event

        publish_event(
            "queue",
            {
                "action": "invite_accepted",
                "invite_id": invite.get("invite_id"),
                "party_id": party_a.get("party_id"),
                "from_discord_id": invite.get("from_discord_id"),
                "target_discord_id": invite.get("target_discord_id"),
            },
        )
        return {"kind": "invite", "party": party_a}

    # Inviter's party always absorbs the invitee's party.
    survivor, absorbed = party_a, party_b

    if not can_merge_as_allies(survivor.get("lineup", []), absorbed.get("lineup", [])):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Can't combine these groups — host needs a bagger for the last slot "
            "(or the combined roster wouldn't fit).",
        )

    combined_lineup = list(survivor.get("lineup", []))
    existing_ids = {p.get("discord_id") for p in combined_lineup}
    for player in absorbed.get("lineup", []):
        if player.get("discord_id") in existing_ids:
            continue
        combined_lineup.append(player)

    if len(combined_lineup) > ROSTER_SIZE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Combining these rosters would exceed {ROSTER_SIZE} players.",
        )

    survivor["lineup"] = combined_lineup
    was_hidden = bool(survivor.get("queue_hidden"))
    touch_roster_change(survivor)
    upsert_party(survivor)
    finalize_roster_change(survivor, was_hidden=was_hidden)
    cancel_party(absorbed["party_id"])
    _resync_billboard_from_party(survivor)

    from utils.pending_outbound import (
        clear_outbound_pending_for_party,
        clear_outbound_pending_for_user,
    )

    clear_outbound_pending_for_party(survivor.get("party_id"))
    clear_outbound_pending_for_party(absorbed.get("party_id"))
    for player in absorbed.get("lineup", []):
        try:
            clear_outbound_pending_for_user(int(player.get("discord_id")))
        except (TypeError, ValueError):
            pass

    invite["status"] = "accepted"
    upsert_party_invite(invite)
    delete_party_invite(invite["invite_id"])
    from utils.event_bus import publish_event

    publish_event(
        "queue",
        {
            "action": "invite_accepted",
            "invite_id": invite.get("invite_id"),
            "party_id": survivor.get("party_id"),
            "from_discord_id": invite.get("from_discord_id"),
            "target_discord_id": invite.get("target_discord_id"),
        },
    )
    return {"kind": "invite", "party": survivor}


def _deny_party_invite(invite: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    if invite.get("status") != "pending":
        raise HTTPException(status.HTTP_410_GONE, "This invite is no longer active.")
    if user.discord_id not in (int(invite.get("target_discord_id")), int(invite.get("from_discord_id"))):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This invite does not belong to you.")

    delete_party_invite(invite["invite_id"])
    from utils.event_bus import publish_event

    publish_event(
        "queue",
        {
            "action": "invite_denied",
            "invite_id": invite.get("invite_id"),
            "party_id": invite.get("party_id"),
            "from_discord_id": invite.get("from_discord_id"),
            "target_discord_id": invite.get("target_discord_id"),
        },
    )
    return {"kind": "invite", "status": "denied"}


@router.post("/requests/{request_id}/accept")
def accept_request(
    request_id: str,
    user: CurrentUser = Depends(require_linked_fc),
) -> dict[str, Any]:
    kind, request = _find_request(request_id)
    if not kind or not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    if kind == "ally":
        return _accept_ally_request(request, user)
    if kind == "match":
        return _accept_match_request(request, user)
    return _accept_party_invite(request, user)


@router.post("/requests/{request_id}/deny")
def deny_request(
    request_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    kind, request = _find_request(request_id)
    if not kind or not request:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    if kind == "ally":
        return _deny_ally_request(request, user)
    if kind == "match":
        return _deny_match_request(request, user)
    return _deny_party_invite(request, user)
