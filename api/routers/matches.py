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


@router.get("/me")
def list_my_matches(user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    mine = [s for s in _all_sessions() if user.discord_id in _participant_ids(s)]
    mine.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return mine


@router.get("/{session_id}")
def get_match(session_id: str, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match session not found.")
    _require_participant(session, user)
    return session


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
