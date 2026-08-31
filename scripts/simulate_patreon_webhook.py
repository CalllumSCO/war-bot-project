#!/usr/bin/env python3
"""Send a sample Patreon members:pledge:create webhook to the local API.

Usage (from repo root):
  PATREON_SKIP_SIGNATURE=1 python scripts/simulate_patreon_webhook.py --discord-id 123456789

Requires the API running on API_BASE_URL (default http://localhost:8000).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate a Patreon membership webhook.")
    parser.add_argument("--discord-id", type=int, required=True, help="Discord user id to grant perks")
    parser.add_argument("--api-base", default=os.getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--tier", choices=["supporter", "supporter_plus"], default="supporter")
    parser.add_argument("--pledge-cents", type=int, default=None, help="Override pledge amount")
    parser.add_argument("--revoke", action="store_true", help="Send former_patron status instead")
    args = parser.parse_args()

    patron_status = "former_patron" if args.revoke else "active_patron"
    if args.pledge_cents is not None:
        pledge_cents = args.pledge_cents
    elif args.tier == "supporter_plus":
        pledge_cents = int(os.getenv("PATREON_SUPPORTER_PLUS_MIN_CENTS", "500"))
    else:
        pledge_cents = int(os.getenv("PATREON_MIN_PLEDGE_CENTS", "100"))

    from datetime import datetime, timedelta, timezone

    next_charge_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    patreon_user_id = f"test-user-{args.discord_id}"
    member_id = f"test-member-{args.discord_id}"

    payload = {
        "data": {
            "id": member_id,
            "type": "member",
            "attributes": {
                "patron_status": patron_status,
                "currently_entitled_amount_cents": pledge_cents,
                "next_charge_date": next_charge_date,
            },
            "relationships": {
                "user": {"data": {"id": patreon_user_id, "type": "user"}},
                "campaign": {"data": {"id": os.getenv("PATREON_CAMPAIGN_ID", "test-campaign"), "type": "campaign"}},
            },
        },
        "included": [
            {
                "type": "user",
                "id": patreon_user_id,
                "attributes": {
                    "social_connections": {
                        "discord": {"user_id": str(args.discord_id)},
                    }
                },
            }
        ],
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{args.api_base.rstrip('/')}/webhooks/patreon",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Patreon-Event": "members:pledge:create",
            "X-Patreon-Signature": "simulate-local",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(resp.status, resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.code, exc.read().decode(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
