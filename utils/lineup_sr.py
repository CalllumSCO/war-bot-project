"""Lineup team SR — TrueSkill for a fixed five-person core roster (RT/CT separate)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

import trueskill

from utils.lineup_store import get_lineup_rating, list_lineups_for_player, upsert_lineup_rating
from utils.mmr import _is_bagger, team_roster_players
from utils.sr import (
    DISPLAY_SCALE,
    MU0,
    SIGMA0,
    display_sr,
    get_player_rating,
    mu_from_sr,
    rank_for_sr,
    tier_label,
)

LINEUP_PLACEMENTS = 5

_env = trueskill.TrueSkill(mu=MU0, sigma=SIGMA0, draw_probability=0.02)


def _normalize_track(war_type: str) -> str:
    return "ct" if str(war_type or "").upper() == "CT" else "rt"


def core_member_ids(lineup: List[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    for player in lineup or []:
        if player.get("ally"):
            continue
        raw = player.get("discord_id")
        if raw is None:
            continue
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


def lineup_fingerprint_ready(lineup: List[Dict[str, Any]]) -> bool:
    return len(core_member_ids(lineup)) == 5


def lineup_id_for(lineup: List[Dict[str, Any]], war_type: str) -> Optional[str]:
    member_ids = core_member_ids(lineup)
    if len(member_ids) != 5:
        return None
    track = _normalize_track(war_type)
    payload = f"{track}:" + ",".join(str(i) for i in member_ids)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _blank_lineup_rating(lineup_id: str, track: str, member_ids: List[int]) -> Dict[str, Any]:
    return {
        "lineup_id": lineup_id,
        "track": track,
        "member_ids": sorted(member_ids),
        "mu": MU0,
        "sigma": SIGMA0,
        "games_together": 0,
        "revealed": False,
        "wins": 0,
        "losses": 0,
    }


def _estimate_opponent_mu(lineup: List[Dict[str, Any]], war_type: str) -> float:
    """Fallback strength when the opponent lineup has no games yet."""
    runners = [p for p in team_roster_players(lineup) if not _is_bagger(p)]
    if not runners:
        return MU0
    scores: List[int] = []
    for player in runners:
        try:
            rating = get_player_rating(
                int(player["discord_id"]),
                war_type,
                bagger=False,
                role=player.get("role"),
            )
            scores.append(int(rating.get("sr") or display_sr(MU0)))
        except Exception:
            continue
    if not scores:
        return MU0
    return mu_from_sr(int(round(sum(scores) / len(scores))))


def _margin_multiplier(point_margin: int) -> float:
    margin = max(1, int(point_margin))
    return min(1.5, 1.0 + (margin / 200.0))


def _apply_lineup_result(
    row: Dict[str, Any],
    *,
    won: bool,
    new_mu: float,
    new_sigma: float,
) -> Dict[str, Any]:
    games = int(row.get("games_together") or 0) + 1
    revealed = bool(row.get("revealed")) or games >= LINEUP_PLACEMENTS
    updated = {
        **row,
        "mu": float(new_mu),
        "sigma": float(new_sigma),
        "games_together": games,
        "revealed": revealed,
        "wins": int(row.get("wins") or 0) + (1 if won else 0),
        "losses": int(row.get("losses") or 0) + (0 if won else 1),
    }
    return upsert_lineup_rating(updated)


def apply_ranked_war_lineup_sr(
    winner_lineup: List[Dict[str, Any]],
    loser_lineup: List[Dict[str, Any]],
    point_margin: int,
    *,
    war_type: str = "RT",
) -> Tuple[Optional[str], Optional[str]]:
    """
    Update lineup team SR for both sides when each has five core players.
    Returns (winner_lineup_id, loser_lineup_id) when updated.
    """
    if not lineup_fingerprint_ready(winner_lineup) or not lineup_fingerprint_ready(loser_lineup):
        return None, None

    track = _normalize_track(war_type)
    win_key = lineup_id_for(winner_lineup, war_type)
    lose_key = lineup_id_for(loser_lineup, war_type)
    if not win_key or not lose_key:
        return None, None

    win_ids = core_member_ids(winner_lineup)
    lose_ids = core_member_ids(loser_lineup)

    win_row = get_lineup_rating(win_key) or _blank_lineup_rating(win_key, track, win_ids)
    lose_row = get_lineup_rating(lose_key) or _blank_lineup_rating(lose_key, track, lose_ids)

    win_ts = _env.create_rating(float(win_row["mu"]), float(win_row["sigma"]))
    if int(lose_row.get("games_together") or 0) > 0:
        lose_mu = float(lose_row["mu"])
        lose_sigma = float(lose_row["sigma"])
    else:
        lose_mu = _estimate_opponent_mu(loser_lineup, war_type)
        lose_sigma = float(SIGMA0)
    lose_ts = _env.create_rating(lose_mu, lose_sigma)

    new_win, new_lose = _env.rate([[win_ts], [lose_ts]], ranks=[0, 1])
    mult = _margin_multiplier(point_margin)

    win_mu = float(win_ts.mu) + (float(new_win[0].mu) - float(win_ts.mu)) * mult
    win_sigma = float(new_win[0].sigma)
    lose_mu = float(lose_ts.mu) + (float(new_lose[0].mu) - float(lose_ts.mu)) * mult
    lose_sigma = float(new_lose[0].sigma)

    _apply_lineup_result(win_row, won=True, new_mu=win_mu, new_sigma=win_sigma)
    _apply_lineup_result(lose_row, won=False, new_mu=lose_mu, new_sigma=lose_sigma)
    return win_key, lose_key


def lineup_display_fields(
    lineup: List[Dict[str, Any]],
    war_type: str,
) -> Dict[str, Any]:
    """Attach lineup team SR fields for API / UI."""
    out: Dict[str, Any] = {
        "lineup_fingerprint_ready": lineup_fingerprint_ready(lineup),
        "lineup_games_together": 0,
        "lineup_revealed": False,
        "lineup_team_sr": None,
        "lineup_team_rank": "unranked",
    }
    key = lineup_id_for(lineup, war_type)
    if not key:
        return out

    row = get_lineup_rating(key)
    if not row:
        return out

    games = int(row.get("games_together") or 0)
    revealed = bool(row.get("revealed"))
    sr = display_sr(float(row.get("mu") or MU0))
    out.update(
        {
            "lineup_id": key,
            "lineup_games_together": games,
            "lineup_revealed": revealed,
            "lineup_team_sr": sr if revealed else None,
            "lineup_team_rank": (
                rank_for_sr(sr, revealed=True) if revealed else "unranked"
            ),
            "lineup_wins": int(row.get("wins") or 0),
            "lineup_losses": int(row.get("losses") or 0),
        }
    )
    return out


def enrich_with_lineup_team(
    payload: Dict[str, Any],
    lineup: List[Dict[str, Any]],
    war_type: str,
) -> Dict[str, Any]:
    out = dict(payload)
    out.update(lineup_display_fields(lineup, war_type))
    return out


def lineup_cards_for_profile(discord_id: int) -> List[Dict[str, Any]]:
    """Summarize revealed + in-progress lineups for /me profile."""
    cards: List[Dict[str, Any]] = []
    for row in list_lineups_for_player(int(discord_id)):
        member_ids = [int(x) for x in row.get("member_ids") or []]
        games = int(row.get("games_together") or 0)
        revealed = bool(row.get("revealed"))
        sr = display_sr(float(row.get("mu") or MU0))
        rank_key = rank_for_sr(sr, revealed=revealed) if revealed else "unranked"
        cards.append(
            {
                "lineup_id": row.get("lineup_id"),
                "track": str(row.get("track") or "rt").upper(),
                "member_ids": [str(x) for x in member_ids],
                "games_together": games,
                "revealed": revealed,
                "team_sr": sr if revealed else None,
                "team_rank": rank_key,
                "team_rank_label": tier_label(rank_key),
                "wins": int(row.get("wins") or 0),
                "losses": int(row.get("losses") or 0),
            }
        )
    return cards
