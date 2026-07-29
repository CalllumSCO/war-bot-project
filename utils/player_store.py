"""Player MMR / ratings — Postgres `players` table or temp/player-mmr.json."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from utils.config import DATA_DIR
from utils.db import get_conn, use_json_stores

DEFAULT_PLAYER_MMR = 10_000
PLAYER_STORE_PATH = os.path.join(DATA_DIR, "player-mmr.json")

TRACKS = ("rt", "ct")
ROLES = ("runner", "bagger")


def _default_ratings(seed: int = DEFAULT_PLAYER_MMR) -> Dict[str, Dict[str, int]]:
    return {
        "rt": {"runner": seed, "bagger": seed},
        "ct": {"runner": seed, "bagger": seed},
    }


def _default_role_record() -> Dict[str, Dict[str, Dict[str, int]]]:
    return {
        track: {role: {"wins": 0, "losses": 0} for role in ROLES}
        for track in TRACKS
    }


def _normalize_track(war_type: str) -> str:
    return "ct" if str(war_type).upper() == "CT" else "rt"


def _normalize_role(*, bagger: bool = False, role: Optional[str] = None) -> str:
    if bagger or str(role or "").lower() == "bagger":
        return "bagger"
    return "runner"


def _is_bagger(player: Dict[str, Any]) -> bool:
    return bool(player.get("bagger") or str(player.get("role") or "").lower() == "bagger")


def _average_ratings(ratings: Dict[str, Dict[str, int]]) -> int:
    vals = [int(ratings[t][r]) for t in TRACKS for r in ROLES]
    return round(sum(vals) / len(vals))


def _blank_player(discord_id: int) -> Dict[str, Any]:
    return {
        "discord_id": discord_id,
        "mmr": DEFAULT_PLAYER_MMR,
        "wins": 0,
        "losses": 0,
        "ratings": _default_ratings(DEFAULT_PLAYER_MMR),
        "record": _default_role_record(),
    }


def _ensure_player_shape(player: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure ratings/record keys exist.
    Does NOT invent per-track W/L from legacy overall totals — that cloned
    RT games onto CT. Use rebuild_players_from_war_results() to backfill.
    """
    ratings = player.get("ratings")
    if not isinstance(ratings, dict):
        ratings = _default_ratings(DEFAULT_PLAYER_MMR)
    else:
        for track in TRACKS:
            track_ratings = ratings.get(track)
            if not isinstance(track_ratings, dict):
                track_ratings = {
                    "runner": DEFAULT_PLAYER_MMR,
                    "bagger": DEFAULT_PLAYER_MMR,
                }
            for role in ROLES:
                if role not in track_ratings:
                    track_ratings[role] = DEFAULT_PLAYER_MMR
                else:
                    track_ratings[role] = int(track_ratings[role])
            ratings[track] = track_ratings

    record = player.get("record")
    if not isinstance(record, dict):
        record = _default_role_record()
    else:
        for track in TRACKS:
            track_record = record.get(track)
            if not isinstance(track_record, dict):
                track_record = {role: {"wins": 0, "losses": 0} for role in ROLES}
            for role in ROLES:
                role_rec = track_record.get(role)
                if not isinstance(role_rec, dict):
                    role_rec = {"wins": 0, "losses": 0}
                track_record[role] = {
                    "wins": int(role_rec.get("wins", 0)),
                    "losses": int(role_rec.get("losses", 0)),
                }
            record[track] = track_record

    player["ratings"] = ratings
    player["record"] = record
    player["mmr"] = _average_ratings(ratings)
    player["wins"] = sum(record[t][r]["wins"] for t in TRACKS for r in ROLES)
    player["losses"] = sum(record[t][r]["losses"] for t in TRACKS for r in ROLES)
    return player


def _parse_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _row_to_player(row: tuple) -> Dict[str, Any]:
    discord_id, mmr, wins, losses, ratings, record = row
    return _ensure_player_shape(
        {
            "discord_id": int(discord_id),
            "mmr": int(mmr or DEFAULT_PLAYER_MMR),
            "wins": int(wins or 0),
            "losses": int(losses or 0),
            "ratings": _parse_json_field(ratings, _default_ratings()),
            "record": _parse_json_field(record, _default_role_record()),
        }
    )


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(PLAYER_STORE_PATH):
        return {"players": {}}
    try:
        with open(PLAYER_STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "players" in data else {"players": {}}
    except json.JSONDecodeError:
        return {"players": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PLAYER_STORE_PATH), exist_ok=True)
    with open(PLAYER_STORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _db_upsert_player(player: Dict[str, Any]) -> None:
    shaped = _ensure_player_shape(dict(player))
    discord_id = int(shaped["discord_id"])
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO players (
                  discord_id, mmr, wins, losses, ratings, record, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW()
                )
                ON CONFLICT (discord_id) DO UPDATE SET
                  mmr = EXCLUDED.mmr,
                  wins = EXCLUDED.wins,
                  losses = EXCLUDED.losses,
                  ratings = EXCLUDED.ratings,
                  record = EXCLUDED.record,
                  updated_at = NOW()
                """,
                (
                    discord_id,
                    int(shaped["mmr"]),
                    int(shaped["wins"]),
                    int(shaped["losses"]),
                    json.dumps(shaped["ratings"]),
                    json.dumps(shaped["record"]),
                ),
            )
        finally:
            cursor.close()


def get_player(discord_id: int) -> Dict[str, Any]:
    if use_json_stores():
        data = _load_all()
        key = str(discord_id)
        if key not in data["players"]:
            return _blank_player(discord_id)
        return _ensure_player_shape(dict(data["players"][key]))

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT discord_id, mmr, wins, losses, ratings, record
                FROM players WHERE discord_id = %s
                """,
                (int(discord_id),),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if not row:
        return _blank_player(discord_id)
    return _row_to_player(row)


def get_rating(
    discord_id: int,
    war_type: str,
    *,
    bagger: bool = False,
    role: Optional[str] = None,
) -> int:
    player = get_player(discord_id)
    track = _normalize_track(war_type)
    role_key = _normalize_role(bagger=bagger, role=role)
    return int(player["ratings"][track][role_key])


def apply_player_delta(
    discord_id: int,
    mmr_delta: int,
    won: bool,
    *,
    war_type: str = "RT",
    bagger: bool = False,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    current = _ensure_player_shape(get_player(discord_id))
    track = _normalize_track(war_type)
    role_key = _normalize_role(bagger=bagger, role=role)

    current["ratings"][track][role_key] = max(
        0, int(current["ratings"][track][role_key]) + int(mmr_delta)
    )
    if won:
        current["record"][track][role_key]["wins"] += 1
    else:
        current["record"][track][role_key]["losses"] += 1

    current["wins"] = sum(current["record"][t][r]["wins"] for t in TRACKS for r in ROLES)
    current["losses"] = sum(current["record"][t][r]["losses"] for t in TRACKS for r in ROLES)
    current["mmr"] = _average_ratings(current["ratings"])
    current["discord_id"] = discord_id

    if use_json_stores():
        data = _load_all()
        data["players"][str(discord_id)] = current
        _save_all(data)
    else:
        _db_upsert_player(current)
    return current


def set_player_mmr(discord_id: int, mmr: int) -> Dict[str, Any]:
    """Set all four ratings to the same value (admin/dev helper)."""
    current = _ensure_player_shape(get_player(discord_id))
    value = max(0, int(mmr))
    current["ratings"] = _default_ratings(value)
    current["mmr"] = value
    current["discord_id"] = discord_id

    if use_json_stores():
        data = _load_all()
        data["players"][str(discord_id)] = current
        _save_all(data)
    else:
        _db_upsert_player(current)
    return current


def replace_all_players(players: Dict[str, Any]) -> None:
    """Bulk replace player MMR rows (used by rebuild)."""
    if use_json_stores():
        _save_all({"players": players})
        return

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            for key, player in players.items():
                shaped = _ensure_player_shape(dict(player))
                shaped["discord_id"] = int(shaped.get("discord_id") or key)
                cursor.execute(
                    """
                    INSERT INTO players (
                      discord_id, mmr, wins, losses, ratings, record, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW()
                    )
                    ON CONFLICT (discord_id) DO UPDATE SET
                      mmr = EXCLUDED.mmr,
                      wins = EXCLUDED.wins,
                      losses = EXCLUDED.losses,
                      ratings = EXCLUDED.ratings,
                      record = EXCLUDED.record,
                      updated_at = NOW()
                    """,
                    (
                        int(shaped["discord_id"]),
                        int(shaped["mmr"]),
                        int(shaped["wins"]),
                        int(shaped["losses"]),
                        json.dumps(shaped["ratings"]),
                        json.dumps(shaped["record"]),
                    ),
                )
        finally:
            cursor.close()


def rebuild_players_from_war_results() -> Dict[str, Any]:
    """
    Reset ratings/records and replay ranked war results in order.
    Applies each stored per-player delta to that war's track + the role
    they played. Allies get personal MMR too (same ± as their side);
    only team averages exclude allies at match time.
    """
    from utils.war_results_store import list_results

    players: Dict[str, Any] = {}

    def ensure(discord_id: int) -> Dict[str, Any]:
        key = str(discord_id)
        if key not in players:
            players[key] = _blank_player(discord_id)
        return players[key]

    results = sorted(
        list_results(),
        key=lambda row: row.get("completed_at") or "",
    )
    applied = 0
    for result in results:
        if str(result.get("mode", "ranked")).lower() != "ranked":
            continue
        war_type = result.get("war_type", "RT")
        team_delta = int(result.get("team_mmr_delta") or 0)
        if team_delta == 0:
            continue

        for lineup_key, won in (("winner_lineup", True), ("loser_lineup", False)):
            for player in result.get(lineup_key) or []:
                raw_id = player.get("discord_id")
                if not raw_id:
                    continue
                delta = team_delta if won else -team_delta

                current = ensure(int(raw_id))
                track = _normalize_track(war_type)
                role_key = _normalize_role(
                    bagger=_is_bagger(player),
                    role=player.get("role"),
                )
                current["ratings"][track][role_key] = max(
                    0, int(current["ratings"][track][role_key]) + delta
                )
                if won:
                    current["record"][track][role_key]["wins"] += 1
                else:
                    current["record"][track][role_key]["losses"] += 1
                applied += 1

    for current in players.values():
        current["wins"] = sum(
            current["record"][t][r]["wins"] for t in TRACKS for r in ROLES
        )
        current["losses"] = sum(
            current["record"][t][r]["losses"] for t in TRACKS for r in ROLES
        )
        current["mmr"] = _average_ratings(current["ratings"])

    replace_all_players(players)
    print(f"Rebuilt MMR for {len(players)} players from {applied} ranked lineup slots.")
    return {"players": players}
