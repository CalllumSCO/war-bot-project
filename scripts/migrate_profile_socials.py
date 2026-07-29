#!/usr/bin/env python3
"""Apply profile social / username columns to Cloud SQL."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local")

from utils.db import get_conn, init_db  # noqa: E402

STATEMENTS = [
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS x_url TEXT",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS bluesky_url TEXT",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS youtube_url TEXT",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS twitch_url TEXT",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS discord_username TEXT",
]


def main() -> int:
    init_db()
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            for sql in STATEMENTS:
                cursor.execute(sql)
                print("ok:", sql)
        finally:
            cursor.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
