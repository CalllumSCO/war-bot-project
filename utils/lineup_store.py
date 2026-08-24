"""Lineup team SR store — Postgres `lineup_ratings` or temp/lineup-ratings.json."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

LINEUP_STORE_PATH = os.path.join(DATA_DIR, "lineup-ratings.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(LINEUP_STORE_PATH):
        return {"lineups": {}}
    try:
        with open(LINEUP_STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "lineups" in data else {"lineups": {}}
    except json.JSONDecodeError:
        return {"lineups": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(LINEUP_STORE_PATH), exist_ok=True)
    with open(LINEUP_STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _row_to_dict(row: tuple) -> Dict[str, Any]:
    (
        lineup_id,
        track,
        member_ids,
        mu,
        sigma,
        games_together,
        revealed,
        wins,
        losses,
    ) = row
    ids = [int(x) for x in (member_ids or [])]
    return {
        "lineup_id": str(lineup_id),
        "track": str(track),
        "member_ids": ids,
        "mu": float(mu),
        "sigma": float(sigma),
        "games_together": int(games_together),
        "revealed": bool(revealed),
        "wins": int(wins),
        "losses": int(losses),
    }


def get_lineup_rating(lineup_id: str) -> Optional[Dict[str, Any]]:
    if use_json_stores():
        return _load_all()["lineups"].get(str(lineup_id))

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT lineup_id, track, member_ids, mu, sigma,
                       games_together, revealed, wins, losses
                FROM lineup_ratings
                WHERE lineup_id = %s
                """,
                (str(lineup_id),),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    return _row_to_dict(row) if row else None


def upsert_lineup_rating(rating: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(rating)
    payload["lineup_id"] = str(payload["lineup_id"])
    payload["member_ids"] = sorted(int(x) for x in payload.get("member_ids") or [])

    if use_json_stores():
        data = _load_all()
        data["lineups"][payload["lineup_id"]] = payload
        _save_all(data)
        return payload

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO lineup_ratings (
                  lineup_id, track, member_ids, mu, sigma,
                  games_together, revealed, wins, losses, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (lineup_id) DO UPDATE SET
                  track = EXCLUDED.track,
                  member_ids = EXCLUDED.member_ids,
                  mu = EXCLUDED.mu,
                  sigma = EXCLUDED.sigma,
                  games_together = EXCLUDED.games_together,
                  revealed = EXCLUDED.revealed,
                  wins = EXCLUDED.wins,
                  losses = EXCLUDED.losses,
                  updated_at = NOW()
                """,
                (
                    payload["lineup_id"],
                    str(payload["track"]),
                    payload["member_ids"],
                    float(payload.get("mu", 25.0)),
                    float(payload.get("sigma", 25.0 / 3.0)),
                    int(payload.get("games_together") or 0),
                    bool(payload.get("revealed")),
                    int(payload.get("wins") or 0),
                    int(payload.get("losses") or 0),
                ),
            )
        finally:
            cursor.close()
    return payload


def list_lineups_for_player(discord_id: int, *, track: Optional[str] = None) -> List[Dict[str, Any]]:
    did = int(discord_id)
    if use_json_stores():
        rows = []
        for row in _load_all()["lineups"].values():
            if did not in [int(x) for x in row.get("member_ids") or []]:
                continue
            if track and str(row.get("track") or "").lower() != str(track).lower():
                continue
            rows.append(dict(row))
        rows.sort(key=lambda r: (r.get("revealed", False), r.get("mu", 0)), reverse=True)
        return rows

    sql = """
        SELECT lineup_id, track, member_ids, mu, sigma,
               games_together, revealed, wins, losses
        FROM lineup_ratings
        WHERE %s = ANY(member_ids)
    """
    params: List[Any] = [did]
    if track:
        sql += " AND track = %s"
        params.append(str(track).lower())
    sql += " ORDER BY revealed DESC, mu DESC, updated_at DESC"

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
        finally:
            cursor.close()
    return [_row_to_dict(row) for row in rows]
