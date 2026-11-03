"""SQLite access layer for TopoTash."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

BASE_DIR = Path(__file__).resolve().parent


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
        migrate_schema(conn)
        conn.commit()
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> dict:
    return {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_diagrams_project_nullable(conn: sqlite3.Connection) -> None:
    """Allow diagrams.project_id to be NULL (library-only diagrams).

    SQLite cannot drop NOT NULL in place, so the table is rebuilt. Foreign keys
    are disabled for the swap; child tables keep referencing ``diagrams``.
    """
    columns = _table_columns(conn, "diagrams")
    if not columns or "project_id" not in columns:
        return
    if not columns["project_id"][3]:  # already nullable
        return
    if conn.in_transaction:
        conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("DROP TABLE IF EXISTS diagrams_migrate")
        conn.execute(
            """CREATE TABLE diagrams_migrate (
                id           TEXT PRIMARY KEY,
                project_id   TEXT REFERENCES projects(id) ON DELETE CASCADE,
                name         TEXT NOT NULL,
                kind         TEXT NOT NULL DEFAULT 'topology',
                description  TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL DEFAULT '{"app":"topotash","version":2,"shapes":{},"order":[],"groups":{},"imagePool":{}}',
                version      INTEGER NOT NULL DEFAULT 0,
                node_count   INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )"""
        )
        conn.execute(
            """INSERT INTO diagrams_migrate
               (id, project_id, name, kind, description, content_json, version, node_count,
                created_at, updated_at)
               SELECT id, project_id, name, kind, description, content_json, version, node_count,
                      created_at, updated_at FROM diagrams"""
        )
        conn.execute("DROP TABLE diagrams")
        conn.execute("ALTER TABLE diagrams_migrate RENAME TO diagrams")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_diagrams_project"
            " ON diagrams(project_id, updated_at DESC)"
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError(f"diagrams migration broke foreign keys: {violations[:3]}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply in-place migrations that CREATE TABLE IF NOT EXISTS cannot express."""
    _migrate_diagrams_project_nullable(conn)


def ensure_schema(app) -> None:
    """Create or upgrade the schema. The script is idempotent, so run it on every start.

    Older builds only initialised a missing database; running ``CREATE TABLE IF NOT
    EXISTS`` each boot keeps existing databases in step when new tables are added.
    """
    init_db(app)


def load_json(raw, default):
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
