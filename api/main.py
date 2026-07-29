"""FastAPI entrypoint for the war-bot companion site.

Run from the repo root, e.g.:
    uvicorn api.main:app --host 0.0.0.0 --port 8000

The sys.path shim below makes `domain`/`utils`/`classes` importable even if
PYTHONPATH was not set explicitly (e.g. `uvicorn api.main:app` run from
inside api/, or a container WORKDIR that differs from the repo root).
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(_REPO_ROOT, ".env.local"))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api.auth.discord import router as auth_router  # noqa: E402
from api.routers import events as events_router  # noqa: E402
from api.routers import matches as matches_router  # noqa: E402
from api.routers import profile as profile_router  # noqa: E402
from api.routers import queue as queue_router  # noqa: E402
from api.routers import wars as wars_router  # noqa: E402


def _allowed_origins() -> list[str]:
    origins: set[str] = set()

    web_base = os.getenv("WEB_BASE_URL", "").strip()
    if web_base:
        origins.add(web_base)

    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(","):
        origin = origin.strip()
        if origin:
            origins.add(origin)

    if os.getenv("PROJECT_ENVIRONMENT", "local").lower() == "local":
        origins.update({"http://localhost:3000", "http://127.0.0.1:3000"})

    return sorted(origins) or ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort DB init: optional/missing tables or an unreachable database
    # should not prevent the API process from starting (health checks, etc).
    try:
        from utils.db import init_db

        init_db()
    except Exception as exc:
        print(f"⚠️ init_db() failed during API startup — continuing degraded: {exc}")

    yield

    try:
        from utils.db import close_db

        close_db()
    except Exception as exc:
        print(f"⚠️ close_db() failed during API shutdown: {exc}")


app = FastAPI(
    title="War Bot Companion API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort catch: store-layer errors (e.g. missing tables) become a
    clean 500 instead of crashing the worker. HTTPException responses are
    handled by FastAPI's own (more specific) handler before this runs."""
    print(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(queue_router.router)
app.include_router(profile_router.router)
app.include_router(matches_router.router)
app.include_router(wars_router.router)
app.include_router(events_router.router)
