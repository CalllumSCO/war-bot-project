"""Persist Patreon member rows and sync supporter status to players.supporter."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from api.services.supporter import ACTIVE_PATRON_STATUSES, pledge_to_tier, set_supporter_tier
from utils.db import get_conn, use_json_stores

_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "temp",
    "patreon_memberships.json",
)


def _campaign_id() -> str | None:
    value = os.getenv("PATREON_CAMPAIGN_ID", "").strip()
    return value or None


def _min_pledge_cents() -> int:
    raw = os.getenv("PATREON_MIN_PLEDGE_CENTS", "100").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 100


def _load_json_store() -> dict[str, Any]:
    try:
        with open(_JSON_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {"memberships": {}, "events": {}}
    except Exception as exc:
        print(f"⚠️ patreon JSON store read failed: {exc}")
        return {"memberships": {}, "events": {}}


def _save_json_store(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_JSON_PATH), exist_ok=True)
    with open(_JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _parse_patreon_date(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _membership_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    next_charge = row[9] if len(row) > 9 else None
    return {
        "member_id": row[0],
        "patreon_user_id": row[1],
        "discord_id": int(row[2]) if row[2] is not None else None,
        "patron_status": row[3],
        "pledge_cents": row[4],
        "campaign_id": row[5],
        "last_event_type": row[6],
        "last_event_at": row[7].isoformat() if row[7] else None,
        "updated_at": row[8].isoformat() if row[8] else None,
        "next_charge_date": next_charge.isoformat() if next_charge else None,
    }


def get_membership_for_discord(discord_id: int) -> dict[str, Any] | None:
    did = int(discord_id)
    if use_json_stores():
        store = _load_json_store()
        for membership in store.get("memberships", {}).values():
            if membership.get("discord_id") == did:
                return membership
        return None

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT member_id, patreon_user_id, discord_id, patron_status,
                           pledge_cents, campaign_id, last_event_type, last_event_at, updated_at,
                           next_charge_date
                    FROM patreon_memberships
                    WHERE discord_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (did,),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
    except Exception as exc:
        print(f"⚠️ get_membership_for_discord failed for {did}: {exc}")
        return None

    if not row:
        return None
    return _membership_row_to_dict(row)


def _is_event_processed(event_key: str) -> bool:
    if use_json_stores():
        store = _load_json_store()
        return event_key in store.get("events", {})
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT 1 FROM patreon_webhook_events WHERE event_key = %s",
                    (event_key,),
                )
                return cursor.fetchone() is not None
            finally:
                cursor.close()
    except Exception:
        return False


def _mark_event_processed(event_key: str, event_type: str) -> None:
    if use_json_stores():
        store = _load_json_store()
        store.setdefault("events", {})[event_key] = {
            "event_type": event_type,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_json_store(store)
        return

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO patreon_webhook_events (event_key, event_type)
                VALUES (%s, %s)
                ON CONFLICT (event_key) DO NOTHING
                """,
                (event_key, event_type),
            )
        finally:
            cursor.close()


def _upsert_membership(
    *,
    member_id: str,
    patreon_user_id: str,
    discord_id: int | None,
    patron_status: str,
    pledge_cents: int | None,
    campaign_id: str | None,
    event_type: str,
    next_charge_date: datetime | None,
    raw: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = {
        "member_id": member_id,
        "patreon_user_id": patreon_user_id,
        "discord_id": discord_id,
        "patron_status": patron_status,
        "pledge_cents": pledge_cents,
        "campaign_id": campaign_id,
        "last_event_type": event_type,
        "last_event_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "next_charge_date": next_charge_date.isoformat() if next_charge_date else None,
        "data": raw,
    }

    if use_json_stores():
        store = _load_json_store()
        store.setdefault("memberships", {})[member_id] = record
        _save_json_store(store)
        return record

    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO patreon_memberships (
                    member_id, patreon_user_id, discord_id, patron_status,
                    pledge_cents, campaign_id, last_event_type, last_event_at,
                    next_charge_date, data, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (member_id) DO UPDATE SET
                    patreon_user_id = EXCLUDED.patreon_user_id,
                    discord_id = COALESCE(EXCLUDED.discord_id, patreon_memberships.discord_id),
                    patron_status = EXCLUDED.patron_status,
                    pledge_cents = EXCLUDED.pledge_cents,
                    campaign_id = EXCLUDED.campaign_id,
                    last_event_type = EXCLUDED.last_event_type,
                    last_event_at = EXCLUDED.last_event_at,
                    next_charge_date = EXCLUDED.next_charge_date,
                    data = EXCLUDED.data,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    member_id,
                    patreon_user_id,
                    discord_id,
                    patron_status,
                    pledge_cents,
                    campaign_id,
                    event_type,
                    now,
                    next_charge_date,
                    json.dumps(raw),
                    now,
                ),
            )
        finally:
            cursor.close()
    return record


def _qualifies_for_supporter(patron_status: str, pledge_cents: int | None, campaign_id: str | None) -> bool:
    expected_campaign = _campaign_id()
    if expected_campaign and campaign_id and campaign_id != expected_campaign:
        return False
    if patron_status not in ACTIVE_PATRON_STATUSES:
        return False
    min_cents = _min_pledge_cents()
    if pledge_cents is not None and pledge_cents < min_cents:
        return False
    return True


def sync_supporter_for_discord(
    discord_id: int,
    *,
    patron_status: str,
    pledge_cents: int | None,
    campaign_id: str | None,
) -> str | None:
    tier = None
    if _qualifies_for_supporter(patron_status, pledge_cents, campaign_id):
        tier = pledge_to_tier(pledge_cents)
    set_supporter_tier(discord_id, tier, source="patreon")
    return tier


def process_member_webhook(
    *,
    event_type: str,
    event_key: str,
    member: dict[str, Any],
    included: list[dict[str, Any]],
) -> dict[str, Any]:
    """Upsert membership from a Patreon members:* webhook and sync supporter flag."""
    if _is_event_processed(event_key):
        return {"status": "duplicate", "event_type": event_type}

    member_id = str(member.get("id") or "")
    if not member_id:
        raise ValueError("Webhook member payload missing id.")

    attrs = member.get("attributes") or {}
    patron_status = str(attrs.get("patron_status") or "unknown")
    pledge_cents = attrs.get("currently_entitled_amount_cents")
    try:
        pledge_cents = int(pledge_cents) if pledge_cents is not None else None
    except (TypeError, ValueError):
        pledge_cents = None

    next_charge_date = _parse_patreon_date(attrs.get("next_charge_date"))

    rel_user = ((member.get("relationships") or {}).get("user") or {}).get("data") or {}
    patreon_user_id = str(rel_user.get("id") or "")
    if not patreon_user_id:
        patreon_user_id = str(attrs.get("patreon_user_id") or member_id)

    campaign_rel = ((member.get("relationships") or {}).get("campaign") or {}).get("data") or {}
    campaign_id = str(campaign_rel.get("id") or "") or None

    discord_id = _discord_id_from_included(included, patreon_user_id)

    membership = _upsert_membership(
        member_id=member_id,
        patreon_user_id=patreon_user_id,
        discord_id=discord_id,
        patron_status=patron_status,
        pledge_cents=pledge_cents,
        campaign_id=campaign_id,
        event_type=event_type,
        next_charge_date=next_charge_date,
        raw={"member": member, "included": included},
    )

    synced = None
    if discord_id is not None:
        synced = sync_supporter_for_discord(
            discord_id,
            patron_status=patron_status,
            pledge_cents=pledge_cents,
            campaign_id=campaign_id,
        )
    else:
        print(
            f"Patreon member {member_id} ({patron_status}) has no linked Discord — "
            "perks will apply after the patron connects Discord on Patreon."
        )

    _mark_event_processed(event_key, event_type)
    return {
        "status": "processed",
        "event_type": event_type,
        "member_id": member_id,
        "discord_id": discord_id,
        "patron_status": patron_status,
        "supporter_active": synced is not None if discord_id is not None else None,
        "supporter_tier": synced,
        "membership": membership,
    }


def _discord_id_from_included(included: list[dict[str, Any]], patreon_user_id: str) -> int | None:
    for item in included or []:
        if item.get("type") != "user":
            continue
        if str(item.get("id") or "") != str(patreon_user_id):
            continue
        attrs = item.get("attributes") or {}
        social = attrs.get("social_connections") or {}
        discord = social.get("discord") or {}
        raw_id = discord.get("user_id") or discord.get("discord_user_id")
        if raw_id is None:
            continue
        try:
            return int(str(raw_id))
        except ValueError:
            continue
    return None
