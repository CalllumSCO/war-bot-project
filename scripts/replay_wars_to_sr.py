#!/usr/bin/env python3
"""Reset player_ratings and replay war_results through the SR / TrueSkill engine.

Fixes incorrect "grandfather reveal" from the first backfill (lanes with <5
games should stay Unranked) and applies bagger dampening + opposing-team
strength for historical wars.

    py scripts/replay_wars_to_sr.py
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
from utils.sr import RUNNER_PLACEMENTS, apply_ranked_war_sr, get_player_ratings_map  # noqa: E402


def _parse(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _scores_from_payload(payload: dict) -> dict[str, float]:
    scores: dict[str, float] = {}
    raw = payload.get("player_scores") or payload.get("scores") or {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            try:
                scores[str(key)] = float(val)
            except (TypeError, ValueError):
                continue
    for side in ("winner_lineup", "loser_lineup"):
        for entry in payload.get(side) or []:
            did = entry.get("discord_id")
            if did is None:
                continue
            if entry.get("score") is not None and str(did) not in scores:
                try:
                    scores[str(did)] = float(entry["score"])
                except (TypeError, ValueError):
                    pass
    return scores


def main() -> int:
    init_db()
    if use_json_stores():
        print("JSON store mode — nothing to replay.")
        return 0

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM player_ratings")
            print("Cleared player_ratings.")
            cursor.execute(
                """
                SELECT id, payload FROM war_results
                ORDER BY completed_at ASC NULLS LAST, id ASC
                """
            )
            wars = cursor.fetchall()
        finally:
            cursor.close()

    print(f"Replaying {len(wars)} war(s) through apply_ranked_war_sr...")
    for war_id, payload_raw in wars:
        payload = _parse(payload_raw)
        mode = str(payload.get("mode") or "ranked").lower()
        if mode != "ranked":
            print(f"  skip war {war_id}: mode={mode}")
            continue
        winner = payload.get("winner_lineup") or []
        loser = payload.get("loser_lineup") or []
        if not winner or not loser:
            print(f"  skip war {war_id}: missing lineups")
            continue
        war_type = str(payload.get("war_type") or "RT").upper()
        margin = int(payload.get("point_margin") or 0)
        scores = _scores_from_payload(payload)
        win_d, lose_d = apply_ranked_war_sr(
            winner,
            loser,
            margin,
            war_type,
            scores=scores,
            update_legacy=False,
        )
        print(
            f"  war {war_id} {war_type} margin={margin}: "
            f"winners={win_d} losers={lose_d}"
        )

    # Safety: never reveal before placement threshold.
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE player_ratings
                SET revealed = (placement_count >= %s)
                """,
                (RUNNER_PLACEMENTS,),
            )
            print(f"Normalized revealed = placement_count >= {RUNNER_PLACEMENTS}.")
        finally:
            cursor.close()

    yoshi = 535940512440385550
    print("\nYoshiChris08 lanes after replay:")
    for key, lane in sorted(get_player_ratings_map(yoshi).items()):
        print(
            f"  {key}: sr={lane.get('sr')} revealed={lane.get('revealed')} "
            f"placements={lane.get('placement_count')}/{RUNNER_PLACEMENTS} "
            f"rank={lane.get('rank')} mu={lane.get('mu'):.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
