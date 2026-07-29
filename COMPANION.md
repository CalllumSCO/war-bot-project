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
