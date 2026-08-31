"""Inbound webhooks (Patreon membership → supporter perks)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from api.services.patreon_membership import process_member_webhook
from api.services.patreon_webhook import (
    event_key,
    extract_member,
    parse_webhook_body,
    skip_signature_check,
    verify_signature,
    webhook_secret,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_MEMBER_EVENTS = frozenset(
    {
        "members:create",
        "members:update",
        "members:delete",
        "members:pledge:create",
        "members:pledge:update",
        "members:pledge:delete",
    }
)


@router.post("/patreon")
async def patreon_webhook(request: Request) -> dict:
    """Patreon members:* webhook — syncs players.supporter from patron status."""
    if not webhook_secret() and not skip_signature_check():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Patreon webhooks are not configured (set PATREON_WEBHOOK_SECRET).",
        )

    body = await request.body()
    signature = request.headers.get("X-Patreon-Signature")
    event_type = (request.headers.get("X-Patreon-Event") or "").strip()

    if not verify_signature(body, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Patreon webhook signature.")

    if event_type not in _MEMBER_EVENTS:
        return {"status": "ignored", "event_type": event_type or "unknown"}

    try:
        payload = parse_webhook_body(body)
        member, included = extract_member(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        result = process_member_webhook(
            event_type=event_type,
            event_key=event_key(signature, event_type, body),
            member=member,
            included=included,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        print(f"Patreon webhook processing failed ({event_type}): {exc}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Webhook processing failed.") from exc

    return result
