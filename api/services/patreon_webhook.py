"""Patreon webhook signature verification and payload parsing."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any


def webhook_secret() -> str:
    return os.getenv("PATREON_WEBHOOK_SECRET", "").strip()


def skip_signature_check() -> bool:
    if os.getenv("PATREON_SKIP_SIGNATURE", "").strip().lower() in ("1", "true", "yes"):
        from utils.config import DEV

        return DEV or os.getenv("PROJECT_ENVIRONMENT", "local").lower() == "local"
    return False


def verify_signature(body: bytes, signature: str | None) -> bool:
    secret = webhook_secret()
    if not secret:
        return skip_signature_check()
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.md5).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def parse_webhook_body(body: bytes) -> dict[str, Any]:
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Webhook body must be a JSON object.")
    return payload


def extract_member(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Webhook payload missing data object.")
    if data.get("type") != "member":
        raise ValueError(f"Unsupported webhook resource type: {data.get('type')!r}")
    included = payload.get("included")
    if included is None:
        included = []
    if not isinstance(included, list):
        raise ValueError("Webhook included must be a list when present.")
    return data, included


def event_key(signature: str | None, event_type: str, body: bytes) -> str:
    if signature:
        return signature.strip()
    digest = hashlib.sha256(body + event_type.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
