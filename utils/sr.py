"""Scrims Rating (SR) — TrueSkill with display scale μ×40."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

import trueskill

from utils.db import get_conn, use_json_stores

MU0 = 25.0
SIGMA0 = 25.0 / 3.0
DISPLAY_SCALE = 40.0
BAGGER_DAMPEN = 0.75
INDIV_WEIGHT_MIN = 0.92
INDIV_WEIGHT_MAX = 1.08
RUNNER_PLACEMENTS = 5
REVEAL_AFTER_RESET = 3

RANK_FLOORS = [
    ("ruby", 1520),
    ("emerald", 1400),
    ("diamond", 1280),
    ("platinum", 1160),
    ("gold", 1040),
    ("silver", 920),
    ("bronze", 800),
    ("iron", 0),
]

_env = trueskill.TrueSkill(mu=MU0, sigma=SIGMA0, draw_probability=0.02)


def display_sr(mu: float) -> int:
    return int(round(float(mu) * DISPLAY_SCALE))


def mu_from_sr(sr: int) -> float:
    return float(sr) / DISPLAY_SCALE


def rank_for_sr(sr: int, *, revealed: bool, is_paragon: bool = False) -> str:
    if not revealed:
        return "unranked"
    if is_paragon:
        return "paragon"
    for name, floor in RANK_FLOORS:
        if sr >= floor:
            return name
    return "iron"


def tier_label(rank: str) -> str:
    return {
        "unranked": "Unranked",
        "iron": "Iron",
        "bronze": "Bronze",
        "silver": "Silver",
        "gold": "Gold",
        "platinum": "Platinum",
        "diamond": "Diamond",
        "emerald": "Emerald",
        "ruby": "Ruby",
        "paragon": "Paragon",
    }.get(rank, rank.title())


def _blank_rating(discord_id: int, track: str, role: str) -> Dict[str, Any]:
    return {
        "discord_id": discord_id,
        "track": track,
        "role": role,
        "mu": MU0,
        "sigma": SIGMA0,
        "placement_count": 0,
        "revealed": False,
        "season_games": 0,
        "sr": display_sr(MU0),
        "rank": "unranked",
    }


def _normalize_track(war_type: str) -> str:
    return "ct" if str(war_type).upper() == "CT" else "rt"


def _normalize_role(*, bagger: bool = False, role: Optional[str] = None) -> str:
    if bagger or str(role or "").lower() == "bagger":
        return "bagger"
    return "runner"


def _row_to_rating(row: tuple) -> Dict[str, Any]:
    discord_id, track, role, mu, sigma, placement_count, revealed, season_games = row
    sr = display_sr(mu)
    return {
        "discord_id": int(discord_id),
        "track": track,
        "role": role,
        "mu": float(mu),
        "sigma": float(sigma),
        "placement_count": int(placement_count),
        "revealed": bool(revealed),
        "season_games": int(season_games),
        "sr": sr,
        "rank": rank_for_sr(sr, revealed=bool(revealed)),
    }


def get_player_rating(
    discord_id: int,
    war_type: str,
    *,
    bagger: bool = False,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    track = _normalize_track(war_type)
    role_key = _normalize_role(bagger=bagger, role=role)
    return get_player_ratings_map(discord_id).get(f"{track}:{role_key}") or _blank_rating(
        discord_id, track, role_key
    )


def get_player_ratings_map(discord_id: int) -> Dict[str, Dict[str, Any]]:
    """All lanes for a player in one DB round-trip. Keys are `track:role`."""
    out: Dict[str, Dict[str, Any]] = {}
    if use_json_stores():
        for track in ("rt", "ct"):
            for role_key, bagger in (("runner", False), ("bagger", True)):
                out[f"{track}:{role_key}"] = get_player_rating_uncached(
                    discord_id, track.upper(), bagger=bagger, role=role_key
                )
        return out

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT discord_id, track, role, mu, sigma, placement_count, revealed, season_games
                FROM player_ratings
                WHERE discord_id = %s
                """,
                (int(discord_id),),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    for row in rows:
        rating = _row_to_rating(row)
        out[f"{rating['track']}:{rating['role']}"] = rating
    return out


def get_player_rating_uncached(
    discord_id: int,
    war_type: str,
    *,
    bagger: bool = False,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """Single-lane read used by JSON-store fallback (and internal map build)."""
    track = _normalize_track(war_type)
    role_key = _normalize_role(bagger=bagger, role=role)
    if use_json_stores():
        from utils.player_store import get_rating

        legacy = get_rating(discord_id, war_type, bagger=bagger, role=role)
        approx_sr = int(round(legacy / 10.0)) if legacy > 2000 else int(legacy)
        mu = mu_from_sr(approx_sr if approx_sr else 1000)
        return {
            **_blank_rating(discord_id, track, role_key),
            "mu": mu,
            "sr": display_sr(mu),
            "rank": "unranked",
        }

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT discord_id, track, role, mu, sigma, placement_count, revealed, season_games
                FROM player_ratings
                WHERE discord_id = %s AND track = %s AND role = %s
                """,
                (int(discord_id), track, role_key),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if not row:
        return _blank_rating(discord_id, track, role_key)
    return _row_to_rating(row)


def _upsert_rating(rating: Dict[str, Any]) -> None:
    if use_json_stores():
        return
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO player_ratings (
                  discord_id, track, role, mu, sigma, placement_count, revealed, season_games, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (discord_id, track, role) DO UPDATE SET
                  mu = EXCLUDED.mu,
                  sigma = EXCLUDED.sigma,
                  placement_count = EXCLUDED.placement_count,
                  revealed = EXCLUDED.revealed,
                  season_games = EXCLUDED.season_games,
                  updated_at = NOW()
                """,
                (
                    int(rating["discord_id"]),
                    rating["track"],
                    rating["role"],
                    float(rating["mu"]),
                    float(rating["sigma"]),
                    int(rating["placement_count"]),
                    bool(rating["revealed"]),
                    int(rating["season_games"]),
                ),
            )
        finally:
            cursor.close()


def _indiv_weight(score: Optional[float], mean_score: float) -> float:
    if score is None or mean_score <= 0:
        return 1.0
    ratio = float(score) / float(mean_score)
    return max(INDIV_WEIGHT_MIN, min(INDIV_WEIGHT_MAX, ratio))


def apply_ranked_war_sr(
    winner_lineup: List[Dict[str, Any]],
    loser_lineup: List[Dict[str, Any]],
    point_margin: int,
    war_type: str = "RT",
    *,
    scores: Optional[Dict[str, float]] = None,
    update_legacy: bool = True,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Update TrueSkill for both teams. Returns (winner_sr_deltas, loser_sr_deltas)
    keyed by discord_id string. Opposing strength is primary; /180 is a narrow nudge.

    Set update_legacy=False when replaying historical wars so W/L / legacy MMR
    columns are not double-counted.
    """
    scores = scores or {}
    winner_players = [p for p in winner_lineup if p.get("discord_id")]
    loser_players = [p for p in loser_lineup if p.get("discord_id")]
    if not winner_players or not loser_players:
        return {}, {}

    def rating_for(player: Dict[str, Any]) -> Dict[str, Any]:
        return get_player_rating(
            int(player["discord_id"]),
            war_type,
            bagger=bool(player.get("bagger") or str(player.get("role") or "").lower() == "bagger"),
            role=player.get("role"),
        )

    win_ratings = [rating_for(p) for p in winner_players]
    lose_ratings = [rating_for(p) for p in loser_players]

    win_ts = [_env.create_rating(r["mu"], r["sigma"]) for r in win_ratings]
    lose_ts = [_env.create_rating(r["mu"], r["sigma"]) for r in lose_ratings]

    new_win, new_lose = _env.rate([win_ts, lose_ts], ranks=[0, 1])

    score_vals = [float(scores[str(p["discord_id"])]) for p in winner_players + loser_players if str(p["discord_id"]) in scores]
    mean_score = (sum(score_vals) / len(score_vals)) if score_vals else 90.0

    win_deltas: Dict[str, int] = {}
    lose_deltas: Dict[str, int] = {}

    for player, before, after in zip(winner_players, win_ratings, new_win):
        did = str(player["discord_id"])
        role = _normalize_role(
            bagger=bool(player.get("bagger") or str(player.get("role") or "").lower() == "bagger"),
            role=player.get("role"),
        )
        mu_delta = float(after.mu) - float(before["mu"])
        if role == "bagger":
            mu_delta *= BAGGER_DAMPEN
        else:
            w = _indiv_weight(scores.get(did), mean_score)
            mu_delta *= w
        # Mild margin boost
        mu_delta *= min(1.5, 1.0 + max(0, int(point_margin)) / 200.0)

        new_mu = float(before["mu"]) + mu_delta
        new_sigma = float(after.sigma)
        if role == "bagger":
            # Keep bagger sigma from collapsing too fast
            new_sigma = max(new_sigma, float(before["sigma"]) * 0.85 + SIGMA0 * 0.15)

        placement = int(before["placement_count"]) + 1
        need = RUNNER_PLACEMENTS if role == "runner" else RUNNER_PLACEMENTS
        revealed = bool(before["revealed"]) or placement >= need
        updated = {
            **before,
            "mu": new_mu,
            "sigma": new_sigma,
            "placement_count": placement,
            "revealed": revealed,
            "season_games": int(before["season_games"]) + 1,
            "sr": display_sr(new_mu),
        }
        _upsert_rating(updated)
        # Mirror approximate integer into legacy mmr column path for bot embeds during transition
        if update_legacy:
            try:
                from utils.player_store import apply_player_delta

                delta_sr = display_sr(new_mu) - display_sr(before["mu"])
                apply_player_delta(
                    int(player["discord_id"]),
                    delta_sr,
                    won=True,
                    war_type=war_type,
                    bagger=role == "bagger",
                    role=role,
                )
                win_deltas[did] = delta_sr
            except Exception:
                win_deltas[did] = display_sr(new_mu) - display_sr(before["mu"])
        else:
            win_deltas[did] = display_sr(new_mu) - display_sr(before["mu"])

    for player, before, after in zip(loser_players, lose_ratings, new_lose):
        did = str(player["discord_id"])
        role = _normalize_role(
            bagger=bool(player.get("bagger") or str(player.get("role") or "").lower() == "bagger"),
            role=player.get("role"),
        )
        mu_delta = float(after.mu) - float(before["mu"])
        if role == "bagger":
            mu_delta *= BAGGER_DAMPEN
        else:
            w = _indiv_weight(scores.get(did), mean_score)
            mu_delta *= w
        mu_delta *= min(1.5, 1.0 + max(0, int(point_margin)) / 200.0)

        new_mu = float(before["mu"]) + mu_delta
        new_sigma = float(after.sigma)
        if role == "bagger":
            new_sigma = max(new_sigma, float(before["sigma"]) * 0.85 + SIGMA0 * 0.15)

        placement = int(before["placement_count"]) + 1
        revealed = bool(before["revealed"]) or placement >= RUNNER_PLACEMENTS
        updated = {
            **before,
            "mu": new_mu,
            "sigma": new_sigma,
            "placement_count": placement,
            "revealed": revealed,
            "season_games": int(before["season_games"]) + 1,
            "sr": display_sr(new_mu),
        }
        _upsert_rating(updated)
        if update_legacy:
            try:
                from utils.player_store import apply_player_delta

                delta_sr = display_sr(new_mu) - display_sr(before["mu"])
                apply_player_delta(
                    int(player["discord_id"]),
                    delta_sr,
                    won=False,
                    war_type=war_type,
                    bagger=role == "bagger",
                    role=role,
                )
                lose_deltas[did] = delta_sr
            except Exception:
                lose_deltas[did] = display_sr(new_mu) - display_sr(before["mu"])
        else:
            lose_deltas[did] = display_sr(new_mu) - display_sr(before["mu"])

    return win_deltas, lose_deltas


def soft_reset_lane(
    discord_id: int,
    track: str,
    role: str,
    *,
    g_lane: int,
    g_all: int,
) -> Dict[str, Any]:
    rating = get_player_rating(discord_id, track.upper() if track in ("rt", "ct") else track, role=role)
    # normalize track key
    track = track.lower()
    role = role.lower()
    if use_json_stores():
        return rating

    sr = display_sr(rating["mu"])
    retain = 0.70
    if g_lane == 0 and rating.get("revealed"):
        retain = 0.45
    elif g_lane >= 3 or (g_all >= 10 and g_lane >= 1):
        retain = 0.70
    else:
        retain = 0.70
    if sr >= 1400:
        retain = min(retain, 0.60)

    new_sr = int(round(1000 + retain * (sr - 1000)))
    new_mu = mu_from_sr(new_sr)
    new_sigma = math.sqrt(0.5 * (rating["sigma"] ** 2) + 0.5 * (SIGMA0 ** 2))
    updated = {
        **rating,
        "track": track,
        "role": role,
        "mu": new_mu,
        "sigma": new_sigma,
        "placement_count": 0,
        "revealed": False,
        "sr": new_sr,
        "rank": "unranked",
    }
    _upsert_rating(updated)
    return updated


def seed_bagger_from_mkc(
    discord_id: int,
    track: str,
    *,
    estimated_sr: int,
) -> Dict[str, Any]:
    """Seed bagger μ from MKC-derived SR estimate; still Unranked until placements."""
    mu = mu_from_sr(int(estimated_sr))
    rating = {
        **_blank_rating(discord_id, track.lower(), "bagger"),
        "mu": mu,
        "sigma": SIGMA0,
        "sr": display_sr(mu),
    }
    _upsert_rating(rating)
    return rating
