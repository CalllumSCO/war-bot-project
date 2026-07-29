"""Completed war history for companion profiles + match dashboards."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth.deps import CurrentUser, get_current_user
from api.services.profile_fields import get_extended_profile_fields
from utils.player_profile_store import get_profile
from utils.sr import get_player_rating
from utils.war_results_store import get_result, list_results_for_player
from utils.wiimmfi import team_point_total

router = APIRouter(tags=["wars"])


def _avatar_for(discord_id: int | None) -> str | None:
    if not discord_id:
        return None
    try:
        return get_extended_profile_fields(int(discord_id)).get("discord_avatar_url")
    except Exception:
        return None


def _display_name(entry: dict[str, Any]) -> str:
    did = entry.get("discord_id")
    if did:
        try:
            ext = get_extended_profile_fields(int(did))
            name = ext.get("display_name") or ext.get("discord_username")
            if name:
                return str(name)
        except Exception:
            pass
        try:
            lounge = (get_profile(int(did)) or {}).get("lounge_name")
            if lounge:
                return str(lounge)
        except Exception:
            pass
    return str(entry.get("player") or did or "Unknown")


def _indiv_score(result: dict[str, Any], discord_id: int | None) -> int | None:
    if discord_id is None:
        return None
    scores = result.get("team_scores") or {}
    for side in ("winner", "loser"):
        entry = scores.get(side) or {}
        # Also accept war_id keys from older payloads.
        if not entry.get("players"):
            continue
        for player in entry.get("players") or []:
            if int(player.get("discord_id") or 0) == int(discord_id):
                try:
                    return int(player.get("score"))
                except (TypeError, ValueError):
                    return None
    # Fallback: scan any team_scores values (war_id-keyed).
    for entry in scores.values():
        if not isinstance(entry, dict):
            continue
        for player in entry.get("players") or []:
            if int(player.get("discord_id") or 0) == int(discord_id):
                try:
                    return int(player.get("score"))
                except (TypeError, ValueError):
                    return None
    return None


def _side_totals(result: dict[str, Any]) -> tuple[int | None, int | None]:
    scores = result.get("team_scores") or {}
    winner_entry = scores.get("winner")
    loser_entry = scores.get("loser")
    w = team_point_total(winner_entry) if isinstance(winner_entry, dict) and winner_entry.get("players") else None
    l = team_point_total(loser_entry) if isinstance(loser_entry, dict) and loser_entry.get("players") else None
    return w, l


def _sr_delta_visible(
    discord_id: int | None, war_type: str, entry: dict[str, Any], deltas: dict
) -> int | None:
    if discord_id is None:
        return None
    raw = deltas.get(str(discord_id))
    if raw is None:
        raw = deltas.get(int(discord_id)) if isinstance(deltas, dict) else None
    try:
        delta = int(raw)
    except (TypeError, ValueError):
        return None
    is_bag = bool(entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger")
    try:
        rating = get_player_rating(
            int(discord_id),
            str(war_type or "RT").upper(),
            bagger=is_bag,
            role="bagger" if is_bag else "runner",
        )
        if not rating.get("revealed"):
            return None
    except Exception:
        return None
    return delta


def _enrich_lineup_player(
    entry: dict[str, Any],
    *,
    result: dict[str, Any],
    deltas: dict,
) -> dict[str, Any]:
    did = entry.get("discord_id")
    did_int = int(did) if did is not None else None
    war_type = result.get("war_type") or "RT"
    is_bag = bool(entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger")
    rank = "unranked"
    revealed = False
    if did_int is not None:
        try:
            rating = get_player_rating(
                did_int,
                str(war_type).upper(),
                bagger=is_bag,
                role="bagger" if is_bag else "runner",
            )
            revealed = bool(rating.get("revealed"))
            rank = str(rating.get("rank") or "unranked") if revealed else "unranked"
        except Exception:
            pass
    return {
        "discordId": str(did_int) if did_int is not None else None,
        "displayName": _display_name(entry),
        "avatarUrl": _avatar_for(did_int),
        "role": "bagger" if is_bag else "runner",
        "indiv": _indiv_score(result, did_int),
        "srDelta": _sr_delta_visible(did_int, war_type, entry, deltas),
        "rank": rank,
        "revealed": revealed,
    }


def serialize_war_summary(result: dict[str, Any], *, viewer_id: int | None = None) -> dict[str, Any]:
    deltas = result.get("player_mmr_deltas") or {}
    winner_players = [
        _enrich_lineup_player(p, result=result, deltas=deltas)
        for p in (result.get("winner_lineup") or [])
    ]
    loser_players = [
        _enrich_lineup_player(p, result=result, deltas=deltas)
        for p in (result.get("loser_lineup") or [])
    ]
    w_total, l_total = _side_totals(result)
    margin = result.get("point_margin")
    try:
        margin_i = int(margin) if margin is not None else None
    except (TypeError, ValueError):
        margin_i = None

    viewer_delta = None
    viewer_outcome = None
    if viewer_id is not None:
        for side, players in (("W", winner_players), ("L", loser_players)):
            for p in players:
                if p.get("discordId") and int(p["discordId"]) == int(viewer_id):
                    viewer_outcome = side
                    viewer_delta = p.get("srDelta")
                    break
            if viewer_outcome:
                break

    return {
        "resultId": result.get("result_id"),
        "completedAt": result.get("completed_at"),
        "warType": result.get("war_type") or "RT",
        "mode": result.get("mode") or "ranked",
        "board": result.get("board"),
        "pointMargin": margin_i,
        "winner": {
            "teamName": result.get("winner_team_name") or "Winner",
            "players": winner_players,
            "total": w_total,
        },
        "loser": {
            "teamName": result.get("loser_team_name") or "Loser",
            "players": loser_players,
            "total": l_total,
        },
        "viewerOutcome": viewer_outcome,
        "viewerSrDelta": viewer_delta,
    }


def serialize_war_detail(result: dict[str, Any], *, viewer_id: int | None = None) -> dict[str, Any]:
    summary = serialize_war_summary(result, viewer_id=viewer_id)
    w_total = summary["winner"].get("total")
    l_total = summary["loser"].get("total")
    margin = summary.get("pointMargin")
    if w_total is not None and l_total is not None:
        scrim_plus = w_total - l_total
    elif isinstance(margin, int):
        scrim_plus = margin
    else:
        scrim_plus = None
    summary["scrimPlusMinus"] = scrim_plus
    summary["rxx"] = result.get("rxx")
    summary["syncMethod"] = result.get("sync_method")
    return summary


@router.get("/users/{discord_id}/wars")
def list_user_wars(
    discord_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    rows = list_results_for_player(discord_id, limit=limit)
    return {
        "wars": [serialize_war_summary(r, viewer_id=discord_id) for r in rows],
    }


@router.get("/me/wars")
def list_my_wars(
    limit: int = Query(default=20, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    rows = list_results_for_player(user.discord_id, limit=limit)
    return {
        "wars": [serialize_war_summary(r, viewer_id=user.discord_id) for r in rows],
    }


@router.get("/wars/{result_id}")
def get_war_result(
    result_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = get_result(result_id)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "War result not found.")
    return serialize_war_detail(result, viewer_id=user.discord_id)
