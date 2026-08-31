"""Public SR leaderboards."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from utils.leaderboard import DEFAULT_SCOPE, LeaderboardScope, fetch_leaderboard, leaderboard_meta

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard/meta")
def get_leaderboard_meta() -> dict:
    return leaderboard_meta()


@router.get("/leaderboard")
def get_leaderboard(
    track: str = Query("rt", pattern="^(rt|ct)$"),
    role: str = Query("runner", pattern="^(runner|bagger)$"),
    scope: LeaderboardScope = Query(DEFAULT_SCOPE, pattern="^(all|elite)$"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
) -> dict:
    try:
        return fetch_leaderboard(track=track, role=role, scope=scope, limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc
