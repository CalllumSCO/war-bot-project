#!/usr/bin/env python3
"""One-shot import of temp/*.json durable data into Cloud SQL."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local")

from utils.boards import ALL_BOARD_KEYS  # noqa: E402
from utils.config import DATA_DIR  # noqa: E402
from utils.db import get_conn, init_db, use_json_stores  # noqa: E402
from utils.player_store import (  # noqa: E402
    DEFAULT_PLAYER_MMR,
    _blank_player,
    _default_ratings,
    _default_role_record,
    _ensure_player_shape,
)


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return fallback


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return cursor.fetchone() is not None


def _import_players() -> int:
    profiles = _read_json(Path(DATA_DIR) / "player-profiles.json", {"profiles": {}}).get(
        "profiles", {}
    )
    mmr_data = _read_json(Path(DATA_DIR) / "player-mmr.json", {"players": {}}).get(
        "players", {}
    )

    ids = set(profiles.keys()) | set(mmr_data.keys())
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            for key in ids:
                discord_id = int(key)
                profile = profiles.get(key) or {}
                player = _ensure_player_shape(
                    mmr_data.get(key) or _blank_player(discord_id)
                )
                cursor.execute(
                    """
                    INSERT INTO players (
                      discord_id, friend_code, lounge_name, lounge_player_id,
                      link_source, lounge_verified, last_fc_verified_at,
                      mmr, wins, losses, ratings, record, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s::jsonb, %s::jsonb, NOW()
                    )
                    ON CONFLICT (discord_id) DO UPDATE SET
                      friend_code = COALESCE(EXCLUDED.friend_code, players.friend_code),
                      lounge_name = COALESCE(EXCLUDED.lounge_name, players.lounge_name),
                      lounge_player_id = COALESCE(
                        EXCLUDED.lounge_player_id, players.lounge_player_id
                      ),
                      link_source = COALESCE(EXCLUDED.link_source, players.link_source),
                      lounge_verified = EXCLUDED.lounge_verified OR players.lounge_verified,
                      last_fc_verified_at = COALESCE(
                        EXCLUDED.last_fc_verified_at, players.last_fc_verified_at
                      ),
                      mmr = EXCLUDED.mmr,
                      wins = EXCLUDED.wins,
                      losses = EXCLUDED.losses,
                      ratings = EXCLUDED.ratings,
                      record = EXCLUDED.record,
                      updated_at = NOW()
                    """,
                    (
                        discord_id,
                        profile.get("friend_code"),
                        profile.get("lounge_name"),
                        profile.get("lounge_player_id"),
                        profile.get("link_source"),
                        bool(profile.get("lounge_verified", False)),
                        profile.get("last_fc_verified_at"),
                        int(player.get("mmr", DEFAULT_PLAYER_MMR)),
                        int(player.get("wins", 0)),
                        int(player.get("losses", 0)),
                        json.dumps(player.get("ratings") or _default_ratings()),
                        json.dumps(player.get("record") or _default_role_record()),
                    ),
                )
                count += 1
        finally:
            cursor.close()
    return count


def _import_teams() -> int:
    teams: Dict[str, Any] = _read_json(Path(DATA_DIR) / "teams.json", {"teams": {}}).get(
        "teams", {}
    )
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            for key, team in teams.items():
                guild_id = int(team.get("guild_id") or key)
                cursor.execute(
                    """
                    INSERT INTO teams (guild_id, data, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (guild_id) DO UPDATE SET
                      data = EXCLUDED.data,
                      updated_at = NOW()
                    """,
                    (guild_id, json.dumps(team)),
                )
                count += 1
        finally:
            cursor.close()
    return count


def _import_guild_configs() -> int:
    guilds: Dict[str, Any] = _read_json(
        Path(DATA_DIR) / "guild-config.json", {"guilds": {}}
    ).get("guilds", {})
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            for key, config in guilds.items():
                guild_id = int(config.get("guild_id") or key)
                name = config.get("name") or str(guild_id)
                cursor.execute(
                    """
                    INSERT INTO guild_configs (guild_id, guild_name, data, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW())
                    ON CONFLICT (guild_id) DO UPDATE SET
                      guild_name = EXCLUDED.guild_name,
                      data = EXCLUDED.data,
                      updated_at = NOW()
                    """,
                    (guild_id, name, json.dumps(config)),
                )
                count += 1
        finally:
            cursor.close()
    return count


def _import_war_results() -> int:
    results = _read_json(Path(DATA_DIR) / "war-results.json", {"results": []}).get(
        "results", []
    )
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            for result in results:
                result_id = result.get("result_id")
                completed_at = result.get("completed_at")
                cursor.execute(
                    """
                    INSERT INTO war_results (result_id, completed_at, payload)
                    VALUES (%s, %s::timestamptz, %s::jsonb)
                    ON CONFLICT (result_id) DO UPDATE SET
                      completed_at = EXCLUDED.completed_at,
                      payload = EXCLUDED.payload
                    """,
                    (
                        result_id,
                        completed_at,
                        json.dumps(result),
                    ),
                )
                count += 1
        finally:
            cursor.close()
    return count


def _import_queue_parties() -> int:
    path = Path(DATA_DIR) / "queue-parties.json"
    if not path.exists():
        print("  skip queue_parties (no queue-parties.json)")
        return 0
    parties: Dict[str, Any] = _read_json(path, {"parties": {}}).get("parties", {})
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            if not _table_exists(cursor, "queue_parties"):
                print("  skip queue_parties (table missing)")
                return 0
            for party in parties.values():
                party_id = party.get("party_id")
                if not party_id:
                    continue
                cursor.execute(
                    """
                    INSERT INTO queue_parties (
                      party_id, invite_code, captain_discord_id, guild_id, data, status, updated_at
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, NOW())
                    ON CONFLICT (party_id) DO UPDATE SET
                      invite_code = EXCLUDED.invite_code,
                      captain_discord_id = EXCLUDED.captain_discord_id,
                      guild_id = EXCLUDED.guild_id,
                      data = EXCLUDED.data,
                      status = EXCLUDED.status,
                      updated_at = NOW()
                    """,
                    (
                        party_id,
                        party.get("invite_code"),
                        party.get("captain_discord_id"),
                        party.get("guild_id"),
                        json.dumps(party),
                        party.get("status"),
                    ),
                )
                count += 1
        except Exception as exc:
            print(f"  skip queue_parties ({exc})")
            return 0
        finally:
            cursor.close()
    return count


def _billboard_files() -> List[tuple[str, Path]]:
    billboard_dir = Path(DATA_DIR) / "billboard-data"
    files: List[tuple[str, Path]] = []
    for board in ALL_BOARD_KEYS:
        path = billboard_dir / f"{board}-billboard.json"
        if path.exists():
            files.append((board, path))
            continue
        if board == "rt-ranked":
            legacy = billboard_dir / "rt-billboard.json"
            if legacy.exists():
                files.append((board, legacy))
        elif board == "ct-ranked":
            legacy = billboard_dir / "ct-billboard.json"
            if legacy.exists():
                files.append((board, legacy))
    wars_path = Path(DATA_DIR) / "wars.json"
    if wars_path.exists():
        files.append(("rt-ranked", wars_path))
    return files


def _import_hub_posts() -> int:
    files = _billboard_files()
    if not files:
        print("  skip hub_posts (no billboard/wars JSON)")
        return 0
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            if not _table_exists(cursor, "hub_posts"):
                print("  skip hub_posts (table missing)")
                return 0
            for board, path in files:
                wars = _read_json(path, [])
                if isinstance(wars, dict):
                    wars = wars.get("wars") or wars.get("posts") or list(wars.values())
                if not isinstance(wars, list):
                    continue
                for war in wars:
                    war_id = war.get("war_id")
                    if not war_id:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO hub_posts (
                          war_id, board, party_id, author_id, search_mode, status, data, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                        ON CONFLICT (war_id) DO UPDATE SET
                          board = EXCLUDED.board,
                          party_id = EXCLUDED.party_id,
                          author_id = EXCLUDED.author_id,
                          search_mode = EXCLUDED.search_mode,
                          status = EXCLUDED.status,
                          data = EXCLUDED.data,
                          updated_at = NOW()
                        """,
                        (
                            war_id,
                            board,
                            war.get("party_id"),
                            war.get("author_discord_id"),
                            war.get("search_mode"),
                            war.get("status"),
                            json.dumps(war),
                        ),
                    )
                    count += 1
        except Exception as exc:
            print(f"  skip hub_posts ({exc})")
            return 0
        finally:
            cursor.close()
    return count


def _import_ally_requests() -> int:
    path = Path(DATA_DIR) / "ally-requests.json"
    if not path.exists():
        print("  skip ally_requests (no ally-requests.json)")
        return 0
    requests: Dict[str, Any] = _read_json(path, {"requests": {}}).get("requests", {})
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            if not _table_exists(cursor, "ally_requests"):
                print("  skip ally_requests (table missing)")
                return 0
            for request in requests.values():
                request_id = request.get("request_id")
                if not request_id:
                    continue
                cursor.execute(
                    """
                    INSERT INTO ally_requests (
                      request_id, war_id, requester_discord_id, status, data, updated_at
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (request_id) DO UPDATE SET
                      war_id = EXCLUDED.war_id,
                      requester_discord_id = EXCLUDED.requester_discord_id,
                      status = EXCLUDED.status,
                      data = EXCLUDED.data,
                      updated_at = NOW()
                    """,
                    (
                        request_id,
                        request.get("war_id"),
                        request.get("requester_discord_id"),
                        request.get("status"),
                        json.dumps(request),
                    ),
                )
                count += 1
        except Exception as exc:
            print(f"  skip ally_requests ({exc})")
            return 0
        finally:
            cursor.close()
    return count


def _import_match_requests() -> int:
    path = Path(DATA_DIR) / "match-requests.json"
    if not path.exists():
        print("  skip match_requests (no match-requests.json)")
        return 0
    requests: Dict[str, Any] = _read_json(path, {"requests": {}}).get("requests", {})
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            if not _table_exists(cursor, "match_requests"):
                print("  skip match_requests (table missing)")
                return 0
            for request in requests.values():
                request_id = request.get("request_id")
                if not request_id:
                    continue
                cursor.execute(
                    """
                    INSERT INTO match_requests (
                      request_id, target_war_id, requester_war_id, status, data, updated_at
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (request_id) DO UPDATE SET
                      target_war_id = EXCLUDED.target_war_id,
                      requester_war_id = EXCLUDED.requester_war_id,
                      status = EXCLUDED.status,
                      data = EXCLUDED.data,
                      updated_at = NOW()
                    """,
                    (
                        request_id,
                        request.get("target_war_id"),
                        request.get("requester_war_id"),
                        request.get("status"),
                        json.dumps(request),
                    ),
                )
                count += 1
        except Exception as exc:
            print(f"  skip match_requests ({exc})")
            return 0
        finally:
            cursor.close()
    return count


def _import_match_sessions() -> int:
    path = Path(DATA_DIR) / "match-sessions.json"
    if not path.exists():
        print("  skip match_sessions (no match-sessions.json)")
        return 0
    sessions: Dict[str, Any] = _read_json(path, {"sessions": {}}).get("sessions", {})
    count = 0
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            if not _table_exists(cursor, "match_sessions"):
                print("  skip match_sessions (table missing)")
                return 0
            for session in sessions.values():
                session_id = session.get("session_id")
                if not session_id:
                    continue
                cursor.execute(
                    """
                    INSERT INTO match_sessions (session_id, data, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (session_id) DO UPDATE SET
                      data = EXCLUDED.data,
                      updated_at = NOW()
                    """,
                    (session_id, json.dumps(session)),
                )
                count += 1
        except Exception as exc:
            print(f"  skip match_sessions ({exc})")
            return 0
        finally:
            cursor.close()
    return count


def main() -> int:
    init_db()
    if use_json_stores():
        print("Cloud SQL not available — cannot import. Check secrets/IAM.")
        return 1

    players = _import_players()
    teams = _import_teams()
    guilds = _import_guild_configs()
    wars = _import_war_results()
    parties = _import_queue_parties()
    hubs = _import_hub_posts()
    allies = _import_ally_requests()
    match_reqs = _import_match_requests()
    sessions = _import_match_sessions()
    print(
        f"Import complete: players={players}, teams={teams}, "
        f"guild_configs={guilds}, war_results={wars}, "
        f"queue_parties={parties}, hub_posts={hubs}, "
        f"ally_requests={allies}, match_requests={match_reqs}, "
        f"match_sessions={sessions}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
