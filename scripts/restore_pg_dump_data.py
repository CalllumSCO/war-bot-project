"""Restore COPY data from a plain pg_dump .sql into the current DATABASE_URL DB.

Does not drop schema — truncates listed public tables, then reloads via COPY FROM STDIN.
Usage (repo root):
  py scripts/restore_pg_dump_data.py temp/db-dump/export.sql
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env.local")

from utils.db import get_conn, init_db  # noqa: E402

TABLES = [
    "ally_requests",
    "event_bus",
    "guild_configs",
    "hub_posts",
    "match_messages",
    "match_requests",
    "match_sessions",
    "mkc_tournament_allowlist",
    "party_invites",
    "player_ratings",
    "players",
    "queue_parties",
    "teams",
    "war_results",
]

_SETVAL_RE = re.compile(
    r"SELECT\s+pg_catalog\.setval\('([^']+)',\s*(\d+),\s*(true|false)\s*\);",
    re.IGNORECASE,
)


def _parse_copy_blocks(sql_text: str) -> dict[str, tuple[str, str]]:
    """table -> (column_list_sql, copy_body including trailing newline before \\.)."""
    blocks: dict[str, tuple[str, str]] = {}
    lines = sql_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("COPY public."):
            table = line.split()[1].split(".", 1)[1]
            cols = line[line.index("(") + 1 : line.index(")")]
            i += 1
            data_lines: list[str] = []
            while i < len(lines) and lines[i] != "\\.":
                data_lines.append(lines[i])
                i += 1
            body = ("\n".join(data_lines) + "\n") if data_lines else ""
            blocks[table] = (cols, body)
        i += 1
    return blocks


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: restore_pg_dump_data.py <export.sql>", file=sys.stderr)
        return 2

    dump_path = Path(sys.argv[1])
    if not dump_path.is_file():
        print(f"Missing dump file: {dump_path}", file=sys.stderr)
        return 2

    sql_text = dump_path.read_text(encoding="utf-8")
    init_db()
    blocks = _parse_copy_blocks(sql_text)
    print("tables_in_dump", sorted(blocks.keys()))
    for t, (_, body) in sorted(blocks.items()):
        n = 0 if not body else body.count("\n")
        print(f"  {t}\t{n}")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SET session_replication_role = replica")
        for table in TABLES:
            cur.execute(f'TRUNCATE TABLE public."{table}" CASCADE')

        for table in TABLES:
            if table not in blocks:
                continue
            cols, body = blocks[table]
            if not body.strip():
                continue
            col_sql = ", ".join(f'"{c.strip()}"' for c in cols.split(","))
            copy_sql = f'COPY public."{table}" ({col_sql}) FROM STDIN'
            stream = io.StringIO(body)
            cur.execute(copy_sql, stream=stream)

        cur.execute("SET session_replication_role = DEFAULT")

        for match in _SETVAL_RE.finditer(sql_text):
            seq, val, is_called = match.group(1), int(match.group(2)), match.group(3).lower() == "true"
            cur.execute("SELECT pg_catalog.setval(%s, %s, %s)", (seq, val, is_called))

        conn.commit()

        print("post_restore_counts")
        for table in TABLES:
            cur.execute(f'SELECT count(*) FROM public."{table}"')
            print(f"  {table}\t{cur.fetchone()[0]}")

    print("restore_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
