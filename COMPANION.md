# Companion stack

## One-click local start

**Easiest:** open [`scripts/start_companion.py`](scripts/start_companion.py) and hit **Run** (or F5 with the “Companion: start both” launch config).

Or from Run and Debug, pick **Companion: API + Web** / **Companion: start both (script)**.

Or Terminal → Run Task → **Companion: API + Web**.

That boots:
- API → http://localhost:8000  
- Web → http://localhost:3000  

## Manual Local API
```bash
pip install -r requirements.txt -r api/requirements.txt
# set DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI, JWT_SECRET, WEB_BASE_URL
uvicorn api.main:app --reload --port 8000
```

## Manual Local web
```bash
cd web
npm install
# NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev
```

Discord OAuth redirect should hit `http://localhost:8000/auth/callback` (or your API URL).
After login the API sends you to `http://localhost:3000/auth/callback?token=…`.

## Schema
`utils.db.init_db()` applies `sql/schema.sql` + `sql/schema_v2.sql`.

## Supporter perks (Patreon)

Perks are stored on `players.supporter` and synced from Patreon membership webhooks.

**Perks today (two tiers)**
- **Supporter (live):** queue peeking, custom display name, favorite track on profile, profile accent/badge, match & chat name color
- **Supporter (planned):** Discord Supporter role, season recap export, profile flair
- **Supporter+ (live):** everything in Supporter + vanity `/u/{alias}` URL
- **Supporter+ (planned):** Discord Supporter+ role (separate from Supporter role), Supporter+ profile flair, custom profile picture, beta feature access

**API**
- `POST /webhooks/patreon` — Patreon `members:*` events (signature required in prod)
- `GET /me/supporter` — status + perk list for the logged-in user
- `GET /supporter/perks` — public perk catalog (guide page)
- `GET /supporters/patrons` — thank-you footer patron list
- `POST /admin/supporters/{discord_id}` — manual grant/revoke (`ADMIN_DISCORD_IDS` + JWT)

**Env (API / Cloud Run `war-bot-api`)**
| Variable | Purpose |
|----------|---------|
| `PATREON_WEBHOOK_SECRET` | HMAC secret from Patreon webhook settings |
| `PATREON_CAMPAIGN_ID` | Optional — ignore members from other campaigns |
| `PATREON_MIN_PLEDGE_CENTS` | Minimum pledge for Supporter (default `100`) |
| `PATREON_SUPPORTER_PLUS_MIN_CENTS` | Minimum pledge for Supporter+ (default `500`) |
| `PATREON_PAGE_URL` | Subscribe link shown on `/me/supporter` |
| `SUPPORTER_DISCORD_IDS` | Comma-separated Supporter overrides |
| `SUPPORTER_PLUS_DISCORD_IDS` | Comma-separated Supporter+ overrides |
| `ADMIN_DISCORD_IDS` | Comma-separated admins for manual grants |
| `PATREON_SKIP_SIGNATURE` | Local only — skip signature check when secret unset |


**Patreon setup (when ready)**
1. Create campaign + webhook in Patreon → Developers.
2. URL: `https://<api-host>/webhooks/patreon`
3. Triggers: `members:create`, `members:update`, `members:delete`, `members:pledge:*`
4. Copy webhook secret → `PATREON_WEBHOOK_SECRET` (Secret Manager or Cloud Run env).
5. Patrons must **connect Discord** on Patreon so webhooks include `social_connections.discord`.

**Local test**
```bash
PATREON_SKIP_SIGNATURE=1 uvicorn api.main:app --reload --port 8000
PATREON_SKIP_SIGNATURE=1 python scripts/simulate_patreon_webhook.py --discord-id YOUR_DISCORD_ID
```

