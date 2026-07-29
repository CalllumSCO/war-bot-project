#!/usr/bin/env python3
"""Seed bagger SR from MKCentral placements for every bagger, then replay wars.

Discovers baggers from completed war lineups, looks up each player's MKC record
via friend code (or stored MKC id/url), seeds their bagger lane(s), then clears
and replays ``war_results`` through the SR engine so history stays consistent.

    py scripts/replay_bagger_seeds.py
    py scripts/replay_bagger_seeds.py --track rt
    py scripts/replay_bagger_seeds.py --track both
    py scripts/replay_bagger_seeds.py --discord-id 123456789
    py scripts/replay_bagger_seeds.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local")

from utils.db import get_conn, init_db, use_json_stores  # noqa: E402
from utils.mkcentral import (  # noqa: E402
    estimate_bagger_sr_from_placements,
    parse_mkc_player_id,
    seed_bagger_from_mkc_placements,
    try_seed_bagger_from_fc,
)
from utils.player_profile_store import get_profile  # noqa: E402
from utils.sr import RUNNER_PLACEMENTS, apply_ranked_war_sr, get_player_ratings_map  # noqa: E402


def _parse(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _is_bagger(entry: dict) -> bool:
    return bool(entry.get("bagger") or str(entry.get("role") or "").lower() == "bagger")


def _scores_from_payload(payload: dict) -> dict[str, float]:
    scores: dict[str, float] = {}
    raw = payload.get("player_scores") or payload.get("scores") or {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            try:
                scores[str(key)] = float(val)
            except (TypeError, ValueError):
                continue

    team_scores = payload.get("team_scores") or {}
    if isinstance(team_scores, dict):
        for entry in team_scores.values():
            if not isinstance(entry, dict):
                continue
            for player in entry.get("players") or []:
                did = player.get("discord_id")
                if did is None or player.get("score") is None:
                    continue
                try:
                    scores.setdefault(str(did), float(player["score"]))
                except (TypeError, ValueError):
                    pass

    for side in ("winner_lineup", "loser_lineup"):
        for entry in payload.get(side) or []:
            did = entry.get("discord_id")
            if did is None or entry.get("score") is None:
                continue
            try:
                scores.setdefault(str(did), float(entry["score"]))
            except (TypeError, ValueError):
                pass
    return scores


def _load_wars() -> List[Tuple[Any, dict]]:
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, payload FROM war_results
                ORDER BY completed_at ASC NULLS LAST, id ASC
                """
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    out: List[Tuple[Any, dict]] = []
    for war_id, payload_raw in rows:
        payload = _parse(payload_raw)
        if isinstance(payload, dict):
            out.append((war_id, payload))
    return out


def discover_baggers(wars: Iterable[Tuple[Any, dict]]) -> Set[int]:
    ids: Set[int] = set()
    for _war_id, payload in wars:
        for side in ("winner_lineup", "loser_lineup"):
            for entry in payload.get(side) or []:
                if not _is_bagger(entry):
                    continue
                did = entry.get("discord_id")
                if did is None:
                    continue
                try:
                    ids.add(int(did))
                except (TypeError, ValueError):
                    continue
    return ids


def _profile_mkc_id(discord_id: int) -> Optional[int]:
    profile = get_profile(discord_id) or {}
    for key in ("mkc_player_id", "mkc_url", "mkc"):
        parsed = parse_mkc_player_id(profile.get(key))
        if parsed:
            return parsed
    try:
        from api.services.profile_fields import get_extended_profile_fields

        ext = get_extended_profile_fields(discord_id)
        return parse_mkc_player_id(ext.get("mkc_url"))
    except Exception:
        return None


def _profile_fc(discord_id: int) -> Optional[str]:
    profile = get_profile(discord_id) or {}
    fc = (profile.get("friend_code") or "").strip()
    return fc or None


def _label(discord_id: int) -> str:
    profile = get_profile(discord_id) or {}
    name = profile.get("lounge_name") or profile.get("display_name")
    if name:
        return f"{name} ({discord_id})"
    return str(discord_id)


async def seed_one_bagger(
    discord_id: int,
    *,
    tracks: List[str],
    dry_run: bool,
) -> Dict[str, Any]:
    """Seed bagger lanes for one player. Returns a small status dict."""
    fc = _profile_fc(discord_id)
    mkc_id = _profile_mkc_id(discord_id)
    result: Dict[str, Any] = {
        "discord_id": discord_id,
        "label": _label(discord_id),
        "friend_code": fc,
        "mkc_player_id": mkc_id,
        "tracks": {},
        "ok": False,
        "error": None,
    }

    if not fc and not mkc_id:
        result["error"] = "no friend code or MKC id on profile"
        return result

    for track in tracks:
        try:
            if dry_run:
                result["tracks"][track] = {"dry_run": True, "mkc_player_id": mkc_id}
                result["ok"] = True
                continue

            if fc:
                rating = await try_seed_bagger_from_fc(
                    discord_id,
                    fc,
                    track=track,
                    mkc_player_id=mkc_id,
                )
                if rating:
                    result["tracks"][track] = {
                        "sr": rating.get("sr"),
                        "mu": rating.get("mu"),
                        "source": "fc",
                    }
                    result["ok"] = True
                    # Refresh mkc id if upsert stored it.
                    result["mkc_player_id"] = _profile_mkc_id(discord_id) or mkc_id
                    continue

            if mkc_id:
                rating, seed_sr, used = seed_bagger_from_mkc_placements(
                    discord_id,
                    track=track,
                    mkc_player_id=mkc_id,
                )
                result["tracks"][track] = {
                    "sr": rating.get("sr"),
                    "mu": rating.get("mu"),
                    "seed_sr": seed_sr,
                    "placements": len(used),
                    "check_sr": estimate_bagger_sr_from_placements(used),
                    "source": "mkc_id",
                }
                result["ok"] = True
            else:
                result["tracks"][track] = {
                    "error": "MKC lookup returned no placements",
                }
        except Exception as exc:
            result["tracks"][track] = {"error": str(exc)}
            result["error"] = str(exc)

    if not result["ok"] and not result["error"]:
        result["error"] = "could not seed any track"
    return result


def replay_wars(wars: List[Tuple[Any, dict]], *, focus_ids: Optional[Set[int]] = None) -> None:
    print(f"Replaying {len(wars)} war(s)...")
    for war_id, payload in wars:
        if str(payload.get("mode") or "ranked").lower() != "ranked":
            continue
        winner = payload.get("winner_lineup") or []
        loser = payload.get("loser_lineup") or []
        if not winner or not loser:
            print(f"  skip war {war_id}: missing lineups")
            continue
        war_type = str(payload.get("war_type") or "RT").upper()
        margin = int(payload.get("point_margin") or 0)
        win_d, lose_d = apply_ranked_war_sr(
            winner,
            loser,
            margin,
            war_type,
            scores=_scores_from_payload(payload),
            update_legacy=False,
        )
        if focus_ids:
            bits = []
            for did in sorted(focus_ids):
                key = str(did)
                if key in win_d or key in lose_d:
                    bits.append(f"{did} win={win_d.get(key)} lose={lose_d.get(key)}")
            if bits:
                print(f"  war {war_id}: " + "; ".join(bits))
        else:
            print(f"  war {war_id}: applied (±{margin})")


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed all baggers from MKC placements, then replay war history into SR."
    )
    parser.add_argument(
        "--track",
        choices=("rt", "ct", "both"),
        default="rt",
        help="Which bagger lane(s) to seed (default: rt).",
    )
    parser.add_argument(
        "--discord-id",
        type=int,
        action="append",
        default=[],
        help="Only seed/report this Discord id (repeatable). Default: all baggers in war history.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover baggers and resolve MKC links without writing ratings or replaying.",
    )
    parser.add_argument(
        "--skip-replay",
        action="store_true",
        help="Seed baggers only; do not clear/replay war_results.",
    )
    return parser.parse_args(argv)


async def async_main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    init_db()
    if use_json_stores():
        print("JSON store mode — nothing to seed/replay.")
        return 0

    tracks = ["rt", "ct"] if args.track == "both" else [args.track]
    wars = _load_wars()
    baggers = discover_baggers(wars)
    if args.discord_id:
        focus = {int(x) for x in args.discord_id}
        baggers = {did for did in baggers if did in focus} | {
            did for did in focus if did not in baggers
        }
        # Allow forcing ids even if they never bagged in stored wars.
        baggers |= focus

    if not baggers:
        print("No baggers found in war history.")
        return 0

    print(f"Found {len(baggers)} bagger(s): {', '.join(_label(i) for i in sorted(baggers))}")

    if args.dry_run:
        for did in sorted(baggers):
            status = await seed_one_bagger(did, tracks=tracks, dry_run=True)
            print(
                f"  · {status['label']}: fc={status.get('friend_code') or '—'} "
                f"mkc={status.get('mkc_player_id') or '—'}"
            )
            if status.get("error"):
                print(f"    would skip: {status['error']}")
        print("Dry run — skipped write/replay.")
        return 0

    if not args.skip_replay:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM player_ratings")
                print("Cleared player_ratings.")
            finally:
                cursor.close()

    seed_results: List[Dict[str, Any]] = []
    for did in sorted(baggers):
        status = await seed_one_bagger(did, tracks=tracks, dry_run=False)
        seed_results.append(status)
        if status.get("ok"):
            track_bits = []
            for track, info in (status.get("tracks") or {}).items():
                if info.get("error"):
                    track_bits.append(f"{track}=ERR({info['error']})")
                else:
                    track_bits.append(f"{track}=SR{info.get('sr')}")
            print(f"  ✓ {status['label']}: " + ", ".join(track_bits))
        else:
            print(f"  ✗ {status['label']}: {status.get('error')}")

    seeded_ok = {int(r["discord_id"]) for r in seed_results if r.get("ok")}
    print(f"Seeded {len(seeded_ok)}/{len(baggers)} bagger(s).")

    if args.skip_replay:
        print("Skipped war replay (--skip-replay).")
    else:
        replay_wars(wars, focus_ids=baggers)

        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE player_ratings SET revealed = (placement_count >= %s)",
                    (RUNNER_PLACEMENTS,),
                )
            finally:
                cursor.close()

    print("\nBagger lanes after seed" + ("" if args.skip_replay else " + replay") + ":")
    for did in sorted(baggers):
        print(f"  {_label(did)}")
        lanes = get_player_ratings_map(did)
        bagger_lanes = {
            k: v
            for k, v in lanes.items()
            if "bagger" in str(k).lower()
            or (isinstance(v, dict) and str(v.get("role") or "").lower() == "bagger")
        }
        if not bagger_lanes:
            print("    (no bagger lane)")
            continue
        for key, lane in sorted(bagger_lanes.items()):
            print(
                f"    {key}: sr={lane.get('sr')} revealed={lane.get('revealed')} "
                f"placements={lane.get('placement_count')}/{RUNNER_PLACEMENTS} "
                f"rank={lane.get('rank')} mu={float(lane.get('mu') or 0):.3f}"
            )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
