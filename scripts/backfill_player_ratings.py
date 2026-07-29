#!/usr/bin/env python3
"""Backfill player_ratings (SR / TrueSkill) from legacy players.ratings + record.

Cloud SQL v1 imported MMR/W-L into `players`, but the companion SR table
(`player_ratings`) was empty — profiles looked warless even when war_results
existed. Run once after schema_v2:

    py scripts/backfill_player_ratings.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local")

from utils.db import get_conn, init_db, use_json_stores  # noqa: E402
from utils.player_store import DEFAULT_PLAYER_MMR, TRACKS, ROLES  # noqa: E402
from utils.sr import (  # noqa: E402
    MU0,
    SIGMA0,
    display_sr,
    mu_from_sr,
    rank_for_sr,
)


def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def _legacy_mmr_to_sr(legacy: int) -> int:
    """Map old ~10k-centered MMR onto ~1000-centered display SR."""
    legacy = int(legacy or DEFAULT_PLAYER_MMR)
    if legacy > 2000:
        return int(round(legacy / 10.0))
    return legacy


def _lane_games(record: dict, track: str, role: str) -> int:
    lane = ((record.get(track) or {}).get(role) or {}) if isinstance(record, dict) else {}
    return int(lane.get("wins", 0) or 0) + int(lane.get("losses", 0) or 0)


def backfill() -> int:
    init_db()
    if use_json_stores():
        print("JSON store mode — nothing to backfill into Postgres player_ratings.")
        return 0

    inserted = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT discord_id, ratings, record, wins, losses
                FROM players
                """
            )
            rows = cursor.fetchall()
            for discord_id, ratings_raw, record_raw, wins, losses in rows:
                ratings = _parse_json(ratings_raw) or {}
                record = _parse_json(record_raw) or {}
                for track in TRACKS:
                    track_ratings = ratings.get(track) if isinstance(ratings, dict) else {}
                    if not isinstance(track_ratings, dict):
                        track_ratings = {}
                    for role in ROLES:
                        legacy = int(track_ratings.get(role, DEFAULT_PLAYER_MMR) or DEFAULT_PLAYER_MMR)
                        sr = _legacy_mmr_to_sr(legacy)
                        mu = mu_from_sr(sr) if sr else MU0
                        # Slightly wider sigma for imported estimates.
                        sigma = SIGMA0 * 1.15
                        games = _lane_games(record, track, role)
                        # Stay Unranked until placement threshold (same as live SR).
                        revealed = games >= 5
                        placement_count = games
                        rank = rank_for_sr(display_sr(mu), revealed=revealed)
                        cursor.execute(
                            """
                            INSERT INTO player_ratings (
                              discord_id, track, role, mu, sigma,
                              placement_count, revealed, season_games, updated_at
                            ) VALUES (
                              %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                            )
                            ON CONFLICT (discord_id, track, role) DO UPDATE SET
                              mu = EXCLUDED.mu,
                              sigma = EXCLUDED.sigma,
                              placement_count = GREATEST(
                                player_ratings.placement_count, EXCLUDED.placement_count
                              ),
                              revealed = player_ratings.revealed OR EXCLUDED.revealed,
                              season_games = GREATEST(
                                player_ratings.season_games, EXCLUDED.season_games
                              ),
                              updated_at = NOW()
                            """,
                            (
                                int(discord_id),
                                track,
                                role,
                                float(mu),
                                float(sigma),
                                int(placement_count),
                                bool(revealed),
                                int(games),
                            ),
                        )
                        inserted += 1
                        print(
                            f"  {discord_id} {track}/{role}: "
                            f"legacy={legacy} -> SR={display_sr(mu)} "
                            f"games={games} revealed={revealed} rank={rank}"
                        )
        finally:
            cursor.close()
    return inserted


if __name__ == "__main__":
    n = backfill()
    print(f"Done. Upserted {n} player_ratings lanes.")
