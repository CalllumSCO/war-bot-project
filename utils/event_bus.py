"""Thin wrapper around the Postgres event_bus table."""

from __future__ import annotations

import json
from typing import Any, Dict

from utils.db import get_conn, use_json_stores


def publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    """Best-effort insert into event_bus. No-op for JSON stores."""
    if use_json_stores():
        return
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO event_bus (event_type, payload, created_at)
                    VALUES (%s, %s::jsonb, NOW())
                    """,
                    (event_type, json.dumps(payload)),
                )
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ event_bus publish failed ({event_type}): {exc}")
