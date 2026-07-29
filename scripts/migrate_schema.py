#!/usr/bin/env python3
"""Apply sql/schema.sql to Cloud SQL."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env.local")

from utils.db import apply_schema, init_db, use_json_stores  # noqa: E402


def main() -> int:
    init_db()
    if use_json_stores():
        print("Database not available (JSON stores active). Fix secrets/IAM and retry.")
        return 1
    apply_schema()
    print("Schema applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
