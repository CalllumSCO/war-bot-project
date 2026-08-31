"""SR leaderboard queries — supports all placed players or Ruby+ elite board."""

from __future__ import annotations

import os
from typing import Any, Literal

from api.services.profile_fields import get_extended_profile_fields_many
from utils.db import get_conn, use_json_stores
from utils.sr import RANK_FLOORS, display_sr, rank_for_sr

LeaderboardScope = Literal["all", "elite"]

DEFAULT_SCOPE: LeaderboardScope = (
    "elite" if os.getenv("LEADERBOARD_DEFAULT_SCOPE", "all").strip().lower() == "elite" else "all"
)
ELITE_MIN_SR = int(os.getenv("LEADERBOARD_ELITE_MIN_SR", str(RANK_FLOORS[0][1])))  # Ruby floor (1520)
MAX_LIMIT = 200


def _elite_min_sr() -> int:
    return ELITE_MIN_SR


def scope_label(scope: LeaderboardScope) -> str:
    if scope == "elite":
        return f"Ruby+ ({_elite_min_sr()}+ SR)"
    return "All placed players"


def fetch_leaderboard(
    *,
    track: str = "rt",
    role: str = "runner",
    scope: LeaderboardScope = DEFAULT_SCOPE,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    track_key = "ct" if str(track).lower() == "ct" else "rt"
    role_key = "bagger" if str(role).lower() == "bagger" else "runner"
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))

    rows: list[dict[str, Any]] = []
    total_count = 0
    if use_json_stores():
        rows = _fetch_leaderboard_json(track_key, role_key, scope, limit, offset)
        total_count = len(rows)
    else:
        total_count = _count_leaderboard_db(track_key, role_key, scope)
        rows = _fetch_leaderboard_db(track_key, role_key, scope, limit, offset)

    discord_ids = [int(r["discord_id"]) for r in rows if r.get("discord_id") is not None]
    profiles = get_extended_profile_fields_many(discord_ids) if discord_ids else {}

    entries: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=offset + 1):
        did = int(row["discord_id"])
        extended = profiles.get(did) or {}
        display_name = (
            (extended.get("display_name") or "").strip()
            or (extended.get("discord_username") or "").strip()
            or str(did)
        )
        alias = (extended.get("profile_alias") or "").strip()
        sr = int(row["sr"])
        tier = str(row.get("rank") or rank_for_sr(sr, revealed=True))
        entries.append(
            {
                "rank": idx,
                "discord_id": str(did),
                "display_name": display_name,
                "sr": sr,
                "rank_tier": tier,
                "placement_count": int(row.get("placement_count") or 0),
                "profile_path": f"/u/{alias}" if alias else f"/u/{did}",
                "supporter_tier": extended.get("supporter_tier"),
            }
        )

    return {
        "track": track_key,
        "role": role_key,
        "scope": scope,
        "scope_label": scope_label(scope),
        "elite_min_sr": _elite_min_sr() if scope == "elite" else None,
        "entries": entries,
        "total": total_count,
        "offset": offset,
        "limit": limit,
    }


def _count_leaderboard_db(track: str, role: str, scope: LeaderboardScope) -> int:
    min_sr = _elite_min_sr() if scope == "elite" else None
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                if min_sr is not None:
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM player_ratings
                        WHERE track = %s AND role = %s AND revealed = TRUE
                          AND mu * 40 >= %s
                        """,
                        (track, role, min_sr),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM player_ratings
                        WHERE track = %s AND role = %s AND revealed = TRUE
                        """,
                        (track, role),
                    )
                row = cursor.fetchone()
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ _count_leaderboard_db failed: {exc}")
        return 0
    return int(row[0] or 0) if row else 0


def _fetch_leaderboard_db(
    track: str,
    role: str,
    scope: LeaderboardScope,
    limit: int,
    offset: int = 0,
) -> list[dict[str, Any]]:
    min_sr = _elite_min_sr() if scope == "elite" else None
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                if min_sr is not None:
                    cursor.execute(
                        """
                        SELECT discord_id, mu, placement_count, revealed
                        FROM player_ratings
                        WHERE track = %s AND role = %s AND revealed = TRUE
                          AND mu * 40 >= %s
                        ORDER BY mu DESC
                        OFFSET %s LIMIT %s
                        """,
                        (track, role, min_sr, offset, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT discord_id, mu, placement_count, revealed
                        FROM player_ratings
                        WHERE track = %s AND role = %s AND revealed = TRUE
                        ORDER BY mu DESC
                        OFFSET %s LIMIT %s
                        """,
                        (track, role, offset, limit),
                    )
                raw = cursor.fetchall()
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ fetch_leaderboard_db failed: {exc}")
        return []

    out: list[dict[str, Any]] = []
    for discord_id, mu, placement_count, revealed in raw:
        if not revealed:
            continue
        sr = display_sr(float(mu))
        if min_sr is not None and sr < min_sr:
            continue
        out.append(
            {
                "discord_id": int(discord_id),
                "sr": sr,
                "placement_count": int(placement_count or 0),
                "rank": rank_for_sr(sr, revealed=True),
            }
        )
    return out


def _fetch_leaderboard_json(
    track: str,
    role: str,
    scope: LeaderboardScope,
    limit: int,
    offset: int = 0,
) -> list[dict[str, Any]]:
    # Leaderboard requires Postgres player_ratings; JSON dev stores skip gracefully.
    return []


def leaderboard_meta() -> dict[str, Any]:
    return {
        "scopes": [
            {
                "id": "all",
                "label": "All placed",
                "description": "Everyone who has revealed SR on this lane (finished placements).",
            },
            {
                "id": "elite",
                "label": scope_label("elite"),
                "description": "Ruby and above only — prestige board similar to VALORANT's Radiant leaderboard.",
                "min_sr": _elite_min_sr(),
            },
        ],
        "default_scope": DEFAULT_SCOPE,
        "web_default_scope": "all",
        "discord_default_scope": "elite",
        "tracks": ["rt", "ct"],
        "roles": ["runner", "bagger"],
    }
