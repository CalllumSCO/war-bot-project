"""Manually grant or revoke supporter tiers (admin JWT required)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant or revoke supporter tier via admin API.")
    parser.add_argument("discord_id", type=int, help="Target Discord user id")
    parser.add_argument(
        "--tier",
        choices=["supporter", "supporter_plus", "none"],
        default="supporter",
        help="Tier to grant, or none to revoke",
    )
    parser.add_argument("--api-base", default=os.getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=os.getenv("ADMIN_JWT", ""), help="Admin user JWT")
    args = parser.parse_args()

    if not args.token:
        print("Set ADMIN_JWT to a session token for an ADMIN_DISCORD_IDS user.", file=sys.stderr)
        return 1

    tier = None if args.tier == "none" else args.tier
    body = json.dumps({"tier": tier}).encode("utf-8")
    req = urllib.request.Request(
        f"{args.api_base.rstrip('/')}/admin/supporters/{args.discord_id}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {args.token}",
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
