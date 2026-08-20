"""Matched sessions (post-match war-comm rooms) + their chat messages."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.auth.deps import CurrentUser, get_current_user
from domain.match import get_session, upsert_session
from utils import match_session_store
from utils.db import get_conn, use_json_stores
from utils.match_message_store import append_message, list_messages

router = APIRouter(prefix="/matches", tags=["matches"])


def _all_sessions() -> list[dict[str, Any]]:
    if use_json_stores():
        return list(match_session_store._load_all()["sessions"].values())  # noqa: SLF001

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT data FROM match_sessions")
                rows = cursor.fetchall()
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ Could not list match_sessions: {exc}")
        return []

    sessions = []
    for (data,) in rows:
        sessions.append(data if isinstance(data, dict) else json.loads(data))
    return sessions


def _participant_ids(session: dict[str, Any]) -> set[int]:
    return {
        int(i)
        for i in (session.get("roster_a_ids") or []) + (session.get("roster_b_ids") or [])
        if i is not None
    }


def _require_participant(session: dict[str, Any], user: CurrentUser) -> None:
    if user.discord_id not in _participant_ids(session):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not part of this match.")


def _war_author(lineup: list[dict[str, Any]] | None, war_id: str | None) -> int | None:
    from utils.billboard_store import find_war_across_boards

    if war_id:
        found = find_war_across_boards(str(war_id))
        if found:
            author = found[1].get("author_discord_id")
            if author is not None:
                return int(author)
    for entry in lineup or []:
        did = entry.get("discord_id")
        if did is not None:
            return int(did)
    return None


def _enrich_match_session(session: dict[str, Any]) -> dict[str, Any]:
    from utils.war_cancel_store import find_cancel_for_war

    out = dict(session)
    out["author_a_id"] = _war_author(session.get("lineup_a"), session.get("war_a_id"))
    out["author_b_id"] = _war_author(session.get("lineup_b"), session.get("war_b_id"))
    cancel = None
    for wid in (session.get("war_a_id"), session.get("war_b_id")):
        if not wid:
            continue
        cancel = find_cancel_for_war(str(wid))
        if cancel:
            break
    out["cancel_request"] = cancel
    out["status"] = session.get("status") or "active"
    return out


def _user_war(session: dict[str, Any], user: CurrentUser) -> tuple[dict[str, Any], dict[str, Any]]:
    from utils.billboard_store import find_war_across_boards

    war_a = find_war_across_boards(str(session.get("war_a_id") or ""))
    war_b = find_war_across_boards(str(session.get("war_b_id") or ""))
    if not war_a or not war_b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match wars no longer exist.")
    _, a = war_a
    _, b = war_b
    if user.discord_id in {int(i) for i in (session.get("roster_a_ids") or []) if i is not None}:
        return a, b
    return b, a


@router.get("/me")
def list_my_matches(user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    mine = [_enrich_match_session(s) for s in _all_sessions() if user.discord_id in _participant_ids(s)]
    mine.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return mine


@router.get("/{session_id}")
def get_match(session_id: str, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)
    out = _enrich_match_session(session)
    try:
        your_war, _opp = _user_war(session, user)
        out["is_captain"] = int(your_war.get("author_discord_id") or 0) == int(user.discord_id)
        from utils.war_completion_store import find_pending_for_war
        from utils.wiimmfi import build_score_entry_instructions
        from utils.billboard_store import find_war_across_boards

        pending = find_pending_for_war(str(your_war.get("war_id") or ""))
        if pending and pending.get("status") in ("collecting_scores", "pending_confirmation"):
            scores = pending.get("team_scores") or {}
            winner_name = pending.get("reporter_team_name")
            winner_found = find_war_across_boards(str(pending.get("winner_war_id") or ""))
            if winner_found:
                winner_name = winner_found[1].get("team_name") or winner_name
            out["completion_pending"] = {
                "status": pending.get("status"),
                "manual_fallback": bool(pending.get("manual_fallback")),
                "point_margin": pending.get("point_margin"),
                "reporter_team_name": pending.get("reporter_team_name"),
                "winner_team_name": winner_name,
                "your_team_submitted": str(your_war.get("war_id")) in scores,
                "score_instructions": build_score_entry_instructions(your_war.get("lineup", [])),
                "fallback_reason": pending.get("fallback_reason"),
            }
    except HTTPException:
        out["is_captain"] = False
    return out


class MatchInfoUpdate(BaseModel):
    host_fc: str | None = None
    rxx: str | None = None
    notes: str | None = None


@router.patch("/{session_id}/info")
def patch_match_info(
    session_id: str,
    body: MatchInfoUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    # Any match participant may update host FC / rxx / notes.
    _require_participant(session, user)

    if body.host_fc is not None:
        session["host_fc"] = body.host_fc.strip()
    if body.rxx is not None:
        session["rxx"] = body.rxx.strip()
    if body.notes is not None:
        session["notes"] = body.notes.strip()

    return upsert_session(session)


@router.get("/{session_id}/messages")
def get_messages(
    session_id: str,
    channel: str = Query("match", pattern="^(match|group)$"),
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)
    return list_messages(session_id, channel, limit=limit, before_id=before_id)


class MessageCreate(BaseModel):
    channel: str = Field(default="match", pattern="^(match|group)$")
    body: str


@router.post("/{session_id}/messages", status_code=status.HTTP_201_CREATED)
def post_message(
    session_id: str,
    body: MessageCreate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)

    text = body.body.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message cannot be empty.")

    return append_message(
        session_id,
        body.channel,
        text,
        author_discord_id=user.discord_id,
        author_name=user.display_name,
        source="web",
    )


@router.post("/{session_id}/cancel", status_code=status.HTTP_201_CREATED)
def request_cancel(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    from utils.billboard_store import find_war_across_boards
    from utils.war_cancel_store import create_cancel_request, find_cancel_for_war
    from utils.war_completion_store import find_pending_for_war

    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)

    your_war, opp_war = _user_war(session, user)
    if int(your_war.get("author_discord_id") or 0) != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only your team's captain can request cancel.")
    if find_pending_for_war(str(your_war.get("war_id") or "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Finish or dispute the completion first.")
    if find_cancel_for_war(str(your_war.get("war_id") or "")):
        raise HTTPException(status.HTTP_409_CONFLICT, "A cancel request is already pending.")

    board = session.get("board") or ""
    if not board:
        found = find_war_across_boards(str(your_war.get("war_id") or ""))
        board = found[0] if found else ""
    request = create_cancel_request(board, your_war, opp_war, user.discord_id)
    return {"kind": "cancel", "status": "pending", "request": request}


@router.post("/{session_id}/cancel/accept")
def accept_cancel(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    from utils.war_abort import abort_matched_war_stores
    from utils.war_cancel_store import delete_cancel_request, find_cancel_for_war

    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)

    your_war, _opp = _user_war(session, user)
    request = find_cancel_for_war(str(your_war.get("war_id") or ""))
    if not request or request.get("status") != "pending":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No cancel request to approve.")
    if int(request.get("opponent_captain_id") or 0) != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the opponent captain can approve.")

    from utils.billboard_store import find_war_across_boards

    w1 = find_war_across_boards(str(request.get("requester_war_id") or ""))
    w2 = find_war_across_boards(str(request.get("opponent_war_id") or ""))
    if not w1 or not w2:
        delete_cancel_request(request["request_id"])
        raise HTTPException(status.HTTP_404_NOT_FOUND, "War data missing.")

    abort_matched_war_stores(request["board"], w1[1], w2[1])
    delete_cancel_request(request["request_id"])
    return {"kind": "cancel", "status": "accepted"}


@router.post("/{session_id}/cancel/decline")
def decline_cancel(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    from utils.war_cancel_store import delete_cancel_request, find_cancel_for_war

    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)

    your_war, _opp = _user_war(session, user)
    request = find_cancel_for_war(str(your_war.get("war_id") or ""))
    if not request or request.get("status") != "pending":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No cancel request to decline.")
    if int(request.get("opponent_captain_id") or 0) != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the opponent captain can decline.")

    delete_cancel_request(request["request_id"])
    return {"kind": "cancel", "status": "declined"}


class MatchSubmitBody(BaseModel):
    margin: int = Field(..., ge=0, le=999)
    rxx: str
    reporter_won: bool = True
    scores: str | None = None


@router.post("/{session_id}/submit")
async def submit_match(
    session_id: str,
    body: MatchSubmitBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Start match completion from the web (RXX first, optional manual scores)."""
    from utils.rxx_scoring import build_scores_from_rxx
    from utils.war_cancel_store import find_cancel_for_war
    from utils.war_completion_store import (
        create_pending_collecting_scores,
        find_pending_for_war,
        mark_pending_confirmation,
        upsert_team_scores,
    )
    from utils.wiimmfi import (
        build_team_score_entry,
        normalize_rxx,
        parse_score_line,
    )

    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)

    your_war, opp_war = _user_war(session, user)
    if int(your_war.get("author_discord_id") or 0) != user.discord_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only your team's captain can submit.")
    if find_pending_for_war(str(your_war.get("war_id") or "")):
        raise HTTPException(status.HTTP_409_CONFLICT, "A completion is already in progress.")
    if find_cancel_for_war(str(your_war.get("war_id") or "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A cancel request is pending.")

    board = session.get("board") or ""
    rxx = normalize_rxx(body.rxx)
    if not rxx:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid RXX room code is required.")

    winner_war = your_war if body.reporter_won else opp_war
    loser_war = opp_war if body.reporter_won else your_war

    table_ref, rxx_error = await build_scores_from_rxx(
        rxx, winner_war, loser_war, int(body.margin)
    )
    if table_ref:
        pending = create_pending_collecting_scores(
            board,
            your_war,
            opp_war,
            winner_war["war_id"],
            int(body.margin),
            user.discord_id,
            session.get("session_id"),
            rxx=rxx,
        )
        pending = mark_pending_confirmation(pending["completion_id"], table_ref)
        return {"kind": "submit", "status": "pending_confirmation", "pending": pending}

    pending = create_pending_collecting_scores(
        board,
        your_war,
        opp_war,
        winner_war["war_id"],
        int(body.margin),
        user.discord_id,
        session.get("session_id"),
        rxx=rxx,
        manual_fallback=True,
        fallback_reason=rxx_error,
    )
    if body.scores:
        parsed, parse_error = parse_score_line(body.scores, your_war.get("lineup", []))
        if parse_error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, parse_error)
        pending = upsert_team_scores(
            pending["completion_id"],
            your_war["war_id"],
            build_team_score_entry(your_war, parsed),
        )
    return {
        "kind": "submit",
        "status": "collecting_scores",
        "pending": pending,
        "note": rxx_error or "Manual score entry required.",
    }
