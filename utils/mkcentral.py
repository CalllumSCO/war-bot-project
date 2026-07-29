"""MKCentral bagger seeding — optional FC → registry lookup + 5v5 allowlist."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from utils.db import get_conn, use_json_stores
from utils.sr import seed_bagger_from_mkc

# Verified 5v5 squad/team events (extend over time). GSC weighted highest.
DEFAULT_ALLOWLIST = {
    "gsc": {"display_name": "Grand Star Cup", "weight": 1.5},
    "grand star cup": {"display_name": "Grand Star Cup", "weight": 1.5},
    "battlerock": {"display_name": "MKW Battlerock Tournament", "weight": 1.0},
    "mkw battlerock tournament": {
        "display_name": "MKW Battlerock Tournament",
        "weight": 1.0,
    },
}

MKC_REGISTRY_API = "https://mkcentral.com/api/registry/players"
MKC_PLACEMENTS_API = "https://mkcentral.com/api/tournaments/players/placements"
_HTTP_HEADERS = {
    "User-Agent": "ScrimsHub/1.0 (+https://github.com; bagger-seed)",
    "Accept": "application/json",
}


def normalize_fc(fc: str) -> str:
    digits = re.sub(r"\D", "", fc or "")
    if len(digits) == 12:
        return f"{digits[0:4]}-{digits[4:8]}-{digits[8:12]}"
    return fc.strip()


def parse_mkc_player_id(mkc_url_or_id: Any) -> Optional[int]:
    if mkc_url_or_id is None:
        return None
    if isinstance(mkc_url_or_id, int):
        return mkc_url_or_id
    text = str(mkc_url_or_id).strip()
    if text.isdigit():
        return int(text)
    match = re.search(r"(?:id=|/players/)(\d+)", text)
    if match:
        return int(match.group(1))
    return None


def _http_get_json(url: str, *, timeout: float = 12.0) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers=_HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


async def lookup_mkc_player_by_fc(friend_code: str) -> Optional[Dict[str, Any]]:
    """Best-effort registry lookup by Wii FC. Returns None if not found / API down."""
    fc = normalize_fc(friend_code)
    if not fc:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{MKC_REGISTRY_API}?friend_code={fc}"
            async with session.get(
                url,
                headers=_HTTP_HEADERS,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except Exception:
        return None

    if isinstance(data, dict) and data.get("id"):
        return data
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        for key in ("players", "results", "data"):
            rows = data.get(key)
            if isinstance(rows, list) and rows:
                return rows[0]
    return None


def resolve_event_meta(event_name: str) -> Optional[Dict[str, Any]]:
    """Match tournament name against hardcoded + DB allowlist (substring OK)."""
    key = (event_name or "").strip().lower()
    if not key:
        return None
    if key in DEFAULT_ALLOWLIST:
        return DEFAULT_ALLOWLIST[key]
    for allow_key, meta in DEFAULT_ALLOWLIST.items():
        if allow_key in key or key in allow_key:
            return meta

    if use_json_stores():
        return None
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT event_key, display_name, weight
                    FROM mkc_tournament_allowlist
                    WHERE verified = TRUE
                    """
                )
                for event_key, display_name, weight in cursor.fetchall():
                    allow_key = str(event_key or "").strip().lower()
                    if not allow_key:
                        continue
                    if allow_key == key or allow_key in key or key in allow_key:
                        return {
                            "display_name": display_name or event_key,
                            "weight": float(weight or 1.0),
                        }
            finally:
                cursor.close()
    except Exception:
        return None
    return None


def is_allowlisted_event(event_name: str) -> bool:
    return resolve_event_meta(event_name) is not None


def estimate_bagger_sr_from_placements(placements: List[Dict[str, Any]]) -> int:
    """
    Map verified 5v5 finishes → seed SR around 1000.
    placements: [{event_key|name, place, verified_5v5?}]
    """
    if not placements:
        return 1000
    score = 1000.0
    for row in placements:
        event = str(row.get("event_key") or row.get("name") or "").lower()
        meta = resolve_event_meta(event)
        if not meta and not row.get("verified_5v5"):
            continue
        weight = float((meta or {}).get("weight", 1.0))
        raw_place = row.get("place")
        if raw_place is None:
            continue
        try:
            place = int(raw_place)
        except (TypeError, ValueError):
            continue
        if place <= 0:
            continue
        # Rough: top finishes push up, deep finishes mild
        if place <= 4:
            score += 80 * weight
        elif place <= 8:
            score += 40 * weight
        elif place <= 16:
            score += 15 * weight
        elif place <= 32:
            score += 5 * weight
        else:
            score -= 5 * weight
    return int(max(800, min(1400, round(score))))


def placements_from_mkc_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize MKC /tournaments/players/placements/{id} into seed rows."""
    rows: List[Dict[str, Any]] = []
    for key in (
        "tournament_team_placements",
        "tournament_solo_and_squad_placements",
    ):
        for entry in payload.get(key) or []:
            name = str(entry.get("tournament_name") or "")
            if not name:
                continue
            if entry.get("is_disqualified"):
                continue
            place = entry.get("placement")
            if place is None:
                continue
            meta = resolve_event_meta(name)
            rows.append(
                {
                    "event_key": name.lower(),
                    "name": name,
                    "place": int(place),
                    "tournament_id": entry.get("tournament_id"),
                    "game": entry.get("game"),
                    "mode": entry.get("mode"),
                    "verified_5v5": bool(meta),
                    "weight": float((meta or {}).get("weight", 1.0)) if meta else 1.0,
                }
            )
    return rows


def fetch_player_placements(mkc_player_id: int) -> List[Dict[str, Any]]:
    data = _http_get_json(f"{MKC_PLACEMENTS_API}/{int(mkc_player_id)}")
    if not isinstance(data, dict):
        return []
    return placements_from_mkc_payload(data)


async def fetch_player_placements_async(mkc_player_id: int) -> List[Dict[str, Any]]:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{MKC_PLACEMENTS_API}/{int(mkc_player_id)}"
            async with session.get(
                url,
                headers=_HTTP_HEADERS,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    return placements_from_mkc_payload(data)


def ensure_default_allowlist_rows() -> None:
    """Idempotent seed of known 5v5 events into Postgres allowlist."""
    if use_json_stores():
        return
    rows = [
        ("gsc", "Grand Star Cup", 1.5),
        ("grand star cup", "Grand Star Cup", 1.5),
        ("battlerock", "MKW Battlerock Tournament", 1.0),
        ("mkw battlerock tournament", "MKW Battlerock Tournament", 1.0),
    ]
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                for event_key, display_name, weight in rows:
                    cursor.execute(
                        """
                        INSERT INTO mkc_tournament_allowlist
                          (event_key, display_name, weight, verified)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (event_key) DO UPDATE SET
                          display_name = EXCLUDED.display_name,
                          weight = EXCLUDED.weight,
                          verified = TRUE
                        """,
                        (event_key, display_name, weight),
                    )
            finally:
                cursor.close()
    except Exception:
        pass


def seed_bagger_from_mkc_placements(
    discord_id: int,
    *,
    track: str = "rt",
    mkc_player_id: Optional[int] = None,
    placements: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], int, List[Dict[str, Any]]]:
    """
    Fetch/normalize placements → estimate SR → write bagger lane.
    Returns (rating_row, estimated_sr, used_placements).
    """
    ensure_default_allowlist_rows()
    used = list(placements or [])
    if not used and mkc_player_id:
        used = fetch_player_placements(int(mkc_player_id))
    verified = [
        p
        for p in used
        if p.get("verified_5v5")
        or resolve_event_meta(str(p.get("event_key") or p.get("name") or ""))
    ]
    sr = estimate_bagger_sr_from_placements(verified)
    rating = seed_bagger_from_mkc(discord_id, track, estimated_sr=sr)
    return rating, sr, verified


async def try_seed_bagger_from_fc(
    discord_id: int,
    friend_code: str,
    *,
    track: str = "rt",
    placements: Optional[List[Dict[str, Any]]] = None,
    mkc_player_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Silent preferred path: FC → MKC id → tournament placements → bagger seed.
    Never required to queue.
    """
    ensure_default_allowlist_rows()
    player = await lookup_mkc_player_by_fc(friend_code)
    mkc_id = mkc_player_id
    if player:
        mkc_id = int(player.get("id") or player.get("player_id") or mkc_id or 0) or mkc_id
        try:
            from utils.player_profile_store import upsert_profile

            upsert_profile(
                discord_id,
                mkc_player_id=mkc_id,
                mkc_url=f"https://mkcentral.com/en-us/registry/players/profile?id={mkc_id}",
            )
        except Exception:
            pass

    used = list(placements or [])
    if not used and mkc_id:
        used = await fetch_player_placements_async(int(mkc_id))

    if used:
        rating, _sr, _verified = seed_bagger_from_mkc_placements(
            discord_id,
            track=track,
            placements=used,
        )
        return rating

    if mkc_id:
        return None
    return None
