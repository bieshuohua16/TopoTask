"""SQLite access layer for TopoTash."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "topotash.db"


def utcnow() -> str:
    """Current UTC time in ISO-8601 with a trailing Z (front-end friendly)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        path = current_app.config["DATABASE"]
        conn = sqlite3.connect(path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        g.db = conn
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app) -> None:
    """Create the schema. Safe to call repeatedly."""
    db_path = Path(app.config["DATABASE"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = (BASE_DIR / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def db_session():
    """Small context manager that commits/rolls back the request connection."""
    db = get_db()

    class _Session:
        def __enter__(self):
            return db

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                db.commit()
            else:
                db.rollback()
            return False

    return _Session()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def load_json(raw, default):
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def database_path() -> str:
    """Resolve DB path from env or default, without needing an app context."""
    return os.environ.get("TOPOTASH_DB", str(DEFAULT_DB_PATH))


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
