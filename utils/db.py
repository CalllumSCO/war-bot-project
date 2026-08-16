"""Postgres connection: DATABASE_URL (Supabase/Neon) or Cloud SQL Connector."""

from __future__ import annotations

import os
import ssl
import threading
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any, Generator, Optional
from urllib.parse import unquote, urlparse

from utils.config import DEV, PROJECT_ENV

_connector = None
_connector_lock = threading.Lock()
_initialized = False
_use_json = False
_pool: Queue = Queue(maxsize=10)
_using_database_url = False

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
SCHEMA_V2_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema_v2.sql"


def use_json_stores() -> bool:
    """True when durable stores should keep using temp/*.json."""
    if os.getenv("USE_JSON_STORES", "").strip() in ("1", "true", "True", "yes"):
        return True
    return _use_json or not _initialized


def _env_or_secret(env_key: str, secret_id: str) -> str:
    value = os.getenv(env_key, "").strip()
    if value:
        return value
    from utils.secrets import get_secret

    return get_secret(secret_id)


def _database_url() -> str:
    """Prefer DATABASE_URL; accept legacy `supabase=` alias from .env.local."""
    for key in ("DATABASE_URL", "SUPABASE_DATABASE_URL", "supabase"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    try:
        return _env_or_secret("DATABASE_URL", "database_url")
    except Exception:
        return ""


def _load_db_settings() -> dict[str, str]:
    return {
        "instance": _env_or_secret("CLOUDSQL_INSTANCE", "cloudsql_instance"),
        "database": _env_or_secret("CLOUDSQL_DB", "cloudsql_db"),
        "user": _env_or_secret("CLOUDSQL_USER", "cloudsql_user"),
        "password": _env_or_secret("CLOUDSQL_PASSWORD", "cloudsql_password"),
    }


def _get_connector():
    global _connector
    with _connector_lock:
        if _connector is None:
            from google.cloud.sql.connector import Connector

            _connector = Connector()
        return _connector


def _connect_database_url(url: str):
    import pg8000

    parsed = urlparse(url)
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "localhost"
    port = int(parsed.port or 5432)
    database = unquote((parsed.path or "/postgres").lstrip("/")) or "postgres"
    # Supabase / Neon require TLS. Prefer system/certifi CAs; fall back for
    # pooler chains / local MITM proxies that break verification.
    try:
        import certifi

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ssl_ctx = ssl.create_default_context()

    def _connect_with(ctx: ssl.SSLContext):
        return pg8000.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            ssl_context=ctx,
            timeout=30,
        )

    try:
        return _connect_with(ssl_ctx)
    except Exception as first_exc:
        host_l = (host or "").lower()
        allow_insecure = (
            DEV
            or PROJECT_ENV == "local"
            or os.getenv("DATABASE_SSL_INSECURE", "").strip().lower() in ("1", "true", "yes")
            or "supabase.co" in host_l
            or "supabase.com" in host_l
            or "neon.tech" in host_l
        )
        if not allow_insecure:
            raise
        print(f"⚠️ Postgres TLS verify failed ({first_exc}); retrying without cert verify for {host}")
        insecure = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        insecure.check_hostname = False
        insecure.verify_mode = ssl.CERT_NONE
        return _connect_with(insecure)


def _connect():
    global _using_database_url
    url = _database_url()
    if url:
        _using_database_url = True
        return _connect_database_url(url)
    _using_database_url = False
    settings = _load_db_settings()
    return _get_connector().connect(
        settings["instance"],
        "pg8000",
        user=settings["user"],
        password=settings["password"],
        db=settings["database"],
    )


def _acquire_conn():
    try:
        return _pool.get_nowait()
    except Empty:
        return _connect()


def _release_conn(conn: Any, *, discard: bool = False) -> None:
    if discard:
        try:
            conn.close()
        except Exception:
            pass
        return
    try:
        _pool.put_nowait(conn)
    except Full:
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def get_conn() -> Generator[Any, None, None]:
    """Yield a live pg8000 connection; commit on success, rollback on error."""
    if use_json_stores():
        raise RuntimeError("Database is not initialized (JSON stores active).")
    conn = _acquire_conn()
    discard = False
    try:
        yield conn
        conn.commit()
    except Exception:
        discard = True
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _release_conn(conn, discard=discard)


def _split_sql(sql: str) -> list[str]:
    """Split schema files on semicolons outside dollar-quotes (simple)."""
    parts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if sql.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def apply_schema(conn: Optional[Any] = None) -> None:
    statements = [
        SCHEMA_PATH.read_text(encoding="utf-8"),
        SCHEMA_V2_PATH.read_text(encoding="utf-8") if SCHEMA_V2_PATH.exists() else "",
    ]
    sql = "\n".join(s for s in statements if s.strip())
    chunks = _split_sql(sql)

    def _run(target: Any) -> None:
        cursor = target.cursor()
        try:
            for chunk in chunks:
                cursor.execute(chunk)
        finally:
            cursor.close()

    if conn is not None:
        _run(conn)
        return

    with get_conn() as owned:
        _run(owned)


def init_db() -> None:
    """
    Connect to Postgres (DATABASE_URL or Cloud SQL) and ensure schema exists.
    Prod: fail loud if unreachable.
    Local: USE_JSON_STORES=1 skips DB; otherwise connection errors fall back to JSON.
    """
    global _initialized, _use_json

    if os.getenv("USE_JSON_STORES", "").strip() in ("1", "true", "True", "yes"):
        _use_json = True
        _initialized = False
        print("USE_JSON_STORES=1 — durable stores stay on temp/*.json.")
        return

    try:
        conn = _connect()
        try:
            apply_schema(conn)
            conn.commit()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            finally:
                cursor.close()
            _release_conn(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            raise
    except Exception as exc:
        if not DEV and PROJECT_ENV != "local":
            raise RuntimeError(f"Postgres unavailable in {PROJECT_ENV}: {exc}") from exc
        _use_json = True
        _initialized = False
        print(f"WARNING: Postgres unavailable ({exc}); falling back to JSON stores.")
        return

    _use_json = False
    _initialized = True
    mode = "DATABASE_URL" if _using_database_url else "Cloud SQL connector"
    print(f"Postgres connected via {mode}; durable stores use Postgres.")


def close_db() -> None:
    global _connector, _initialized, _use_json
    while True:
        try:
            conn = _pool.get_nowait()
        except Empty:
            break
        try:
            conn.close()
        except Exception:
            pass
    with _connector_lock:
        if _connector is not None:
            try:
                _connector.close()
            except Exception:
                pass
            _connector = None
    _initialized = False
