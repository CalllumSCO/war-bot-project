"""Replay ranked war_results through lineup team SR.

Usage (repo root):
  py scripts/replay_lineup_ratings.py
  py scripts/replay_lineup_ratings.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv(".env.local")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.db import get_conn, init_db, use_json_stores  # noqa: E402
from utils.lineup_store import LINEUP_STORE_PATH  # noqa: E402
from utils.lineup_sr import apply_ranked_war_lineup_sr  # noqa: E402


def _load_wars() -> list[dict]:
    if use_json_stores():
        path = os.path.join(ROOT, "temp", "war-results.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return list(data.get("results") or data.get("wars") or [])

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT payload FROM war_results
                ORDER BY completed_at ASC, id ASC
                """
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    out = []
    for (payload,) in rows:
        if isinstance(payload, str):
            out.append(json.loads(payload))
        else:
            out.append(payload)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    wars = _load_wars()
    ranked = [w for w in wars if str(w.get("mode") or "ranked").lower() == "ranked"]
    print(f"Replaying {len(ranked)} ranked war(s) through lineup team SR...")

    if args.dry_run:
        touched = 0
        for war in ranked:
            from utils.lineup_sr import lineup_fingerprint_ready

            if lineup_fingerprint_ready(war.get("winner_lineup") or []) and lineup_fingerprint_ready(
                war.get("loser_lineup") or []
            ):
                touched += 1
        print(f"Would update up to {touched} lineup sides.")
        return

    if use_json_stores() and os.path.exists(LINEUP_STORE_PATH):
        os.remove(LINEUP_STORE_PATH)

    if not use_json_stores():
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM lineup_ratings")
            finally:
                cursor.close()

    updates = 0
    for war in ranked:
        win = war.get("winner_lineup") or []
        lose = war.get("loser_lineup") or []
        margin = int(war.get("point_margin") or 1)
        wt = war.get("war_type") or "RT"
        ids = apply_ranked_war_lineup_sr(win, lose, margin, war_type=wt)
        if ids[0] or ids[1]:
            updates += 1

    print(f"Done — processed {updates} war(s) with full lineups.")


if __name__ == "__main__":
    main()
