"""Shared helpers for the TopoTash test suite.

Every test gets its own temporary SQLite database so the developer database
(``topotash.db``) is never touched by the tests.
"""
from __future__ import annotations

import atexit
import os
import tempfile
import unittest
from pathlib import Path

TMP_DIR = Path(tempfile.gettempdir())
_BOOTSTRAP_DB = str(TMP_DIR / f"tt_bootstrap_{os.getpid()}.db")
os.environ.setdefault("TOPOTASH_DB", _BOOTSTRAP_DB)

from app import create_app  # noqa: E402  (env must be set first)


def _unlink_db(path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(path + suffix).unlink()
        except FileNotFoundError:
            pass
        except OSError:  # pragma: no cover - Windows may keep the file briefly open
            pass


@atexit.register
def _cleanup_bootstrap() -> None:  # pragma: no cover - process teardown
    _unlink_db(_BOOTSTRAP_DB)


def shape(node_id: str, text: str = "节点", kind: str = "server", **extra) -> dict:
    """A canvas shape in the format the topology editor stores."""
    item = {
        "id": node_id,
        "type": "shape",
        "kind": kind,
        "x": 100,
        "y": 100,
        "w": 140,
        "h": 70,
        "text": text,
    }
    item.update(extra)
    return item


def canvas(*shapes: dict, **extra) -> dict:
    """A canvas document with the given shapes."""
    shapes_by_id = {s["id"]: s for s in shapes}
    doc = {
        "app": "topotash",
        "version": 2,
        "shapes": shapes_by_id,
        "order": [s["id"] for s in shapes],
        "groups": {},
        "imagePool": {},
    }
    doc.update(extra)
    return doc


class ApiTestCase(unittest.TestCase):
    """Flask test client bound to a throw-away database."""

    def setUp(self):
        name = f"tt_{os.getpid()}_{self.__class__.__name__}_{self._testMethodName}.db"
        self.db_path = str(TMP_DIR / name)
        _unlink_db(self.db_path)
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        from db import close_db

        close_db()
        self.ctx.pop()
        _unlink_db(self.db_path)

    # ------------------------------------------------------------- factories
    def new_project(self, **fields) -> dict:
        payload = {"name": "测试项目", **fields}
        response = self.client.post("/api/projects", json=payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def new_task(self, project_id: str, **fields) -> dict:
        payload = {"project_id": project_id, "title": "测试任务", **fields}
        response = self.client.post("/api/tasks", json=payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def new_diagram(self, project_id: str, doc: dict | None = None, **fields) -> dict:
        payload = {"project_id": project_id, "name": "测试拓扑图", **fields}
        if doc is not None:
            payload["content"] = doc
        response = self.client.post("/api/diagrams", json=payload)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    # -------------------------------------------------------------- helpers
    def get_json(self, path: str, status: int = 200):
        response = self.client.get(path)
        self.assertEqual(response.status_code, status, response.get_data(as_text=True)[:500])
        return response.get_json()

    def api(self, method: str, path: str, payload=None, status: int = 200):
        response = self.client.open(path, method=method, json=payload)
        self.assertEqual(response.status_code, status, response.get_data(as_text=True)[:500])
        return response.get_json() if response.data else None
