"""Unit tests for the shared service / db helpers."""
from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db import dumps, get_db, load_json, migrate_schema, new_id, utcnow
from services import (
    clean_int,
    clean_project_payload,
    clean_stage,
    clean_status,
    clean_task_status,
    content_of,
    create_task_record,
    extract_nodes,
    merge_followup_into_content,
    project_stats,
    sync_diagram_nodes,
    text,
    todo_state,
)
from tests.support import ApiTestCase, canvas, shape


class PureHelperTest(ApiTestCase):
    def test_clean_helpers(self):
        self.assertEqual(clean_stage("poc"), "poc")
        self.assertEqual(clean_stage("nope"), "research")
        self.assertEqual(clean_stage(None, "bidding"), "bidding")
        self.assertEqual(clean_status("won"), "won")
        self.assertEqual(clean_status("nope", "paused"), "paused")
        self.assertEqual(clean_task_status("doing"), "doing")
        self.assertEqual(clean_task_status("nope", "done"), "done")

        self.assertEqual(clean_int("7"), 7)
        self.assertEqual(clean_int("x", fallback=4), 4)
        self.assertEqual(clean_int(9, lo=0, hi=3), 3)
        self.assertEqual(clean_int(-9, lo=0), 0)

        self.assertEqual(text("  a  "), "a")
        self.assertEqual(text(None), "")
        self.assertEqual(text(None, "d"), "d")
        self.assertEqual(text(12), "12")

    def test_project_payload_normalisation(self):
        fields = clean_project_payload(
            {"name": "  P  ", "stage": "poc", "status": "won", "owner": " 王强 ", "junk": 1}
        )
        self.assertEqual(fields["name"], "P")
        self.assertEqual(fields["stage"], "poc")
        self.assertEqual(fields["status"], "won")
        self.assertEqual(fields["owner"], "王强")
        self.assertNotIn("junk", fields)

        with self.assertRaises(Exception):
            clean_project_payload({})

        partial = clean_project_payload({"owner": "李娜"}, partial=True)
        self.assertEqual(partial, {"owner": "李娜"})

    def test_db_json_helpers(self):
        self.assertEqual(load_json('{"a": 1}', {}), {"a": 1})
        self.assertEqual(load_json("not json", {"d": 1}), {"d": 1})
        self.assertEqual(load_json(None, []), [])
        self.assertEqual(load_json("", []), [])
        self.assertEqual(dumps({"a": "中"}), '{"a":"中"}')

        self.assertTrue(re.match(r"^t_[0-9a-f]{12}$", new_id("t_")))
        self.assertTrue(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", utcnow()))


class SchemaMigrationTest(unittest.TestCase):
    def test_diagrams_project_id_becomes_nullable(self):
        path = Path(tempfile.gettempdir()) / f"tt_migrate_{new_id()}.db"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE diagrams (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'topology',
                description TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 0,
                node_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX idx_diagrams_project ON diagrams(project_id, updated_at DESC);
            CREATE TABLE diagram_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                diagram_id TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
                node_key TEXT NOT NULL,
                UNIQUE (diagram_id, node_key)
            );
            INSERT INTO projects(id, name) VALUES ('p1', '项目一');
            INSERT INTO diagrams
                (id, project_id, name, kind, description, content_json, version, node_count,
                 created_at, updated_at)
            VALUES ('d1', 'p1', '旧图', 'topology', '', '{"shapes":{}}', 1, 0,
                    '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO diagram_nodes(diagram_id, node_key) VALUES ('d1', 'n1');
            """
        )
        try:
            self.assertTrue(
                {r[1]: r for r in conn.execute("PRAGMA table_info(diagrams)")}["project_id"][3]
            )
            migrate_schema(conn)
            columns = {r[1]: r for r in conn.execute("PRAGMA table_info(diagrams)")}
            self.assertFalse(columns["project_id"][3])
            self.assertEqual(conn.execute("SELECT name FROM diagrams WHERE id='d1'").fetchone()[0], "旧图")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM diagram_nodes WHERE diagram_id='d1'").fetchone()[0],
                1,
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            conn.execute(
                "INSERT INTO diagrams(id, project_id, name, created_at, updated_at)"
                " VALUES ('d2', NULL, '库图', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
            )
            self.assertIsNone(
                conn.execute("SELECT project_id FROM diagrams WHERE id='d2'").fetchone()[0]
            )
            conn.commit()
        finally:
            conn.close()
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(path) + suffix).unlink()
                except FileNotFoundError:
                    pass

    def test_migration_is_idempotent(self):
        path = Path(tempfile.gettempdir()) / f"tt_migrate_{new_id()}.db"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE diagrams (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'topology',
                description TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 0,
                node_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        try:
            migrate_schema(conn)
            migrate_schema(conn)
            columns = {r[1]: r for r in conn.execute("PRAGMA table_info(diagrams)")}
            self.assertFalse(columns["project_id"][3])
        finally:
            conn.close()
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(path) + suffix).unlink()
                except FileNotFoundError:
                    pass


class NodeIndexTest(ApiTestCase):
    def test_extract_nodes(self):
        doc = canvas(
            shape("n1", "第一行\n第二行"),
            shape("n2", ""),
            shape("e1", "连线", type="connector"),
        )
        nodes = extract_nodes(doc)
        self.assertEqual([n["node_key"] for n in nodes], ["n1", "n2"])
        self.assertEqual(nodes[0]["label"], "第一行")
        self.assertEqual(nodes[1]["label"], "未命名节点")
        self.assertEqual(nodes[0]["kind"], "server")
        self.assertEqual((nodes[0]["x"], nodes[0]["w"]), (100, 140))

    def test_extract_nodes_uses_shape_id_over_key(self):
        doc = {"shapes": {"key1": {"id": "n9", "type": "shape", "text": "X"}}, "order": ["key1"]}
        self.assertEqual(extract_nodes(doc)[0]["node_key"], "n9")

    def test_extract_nodes_truncates_long_labels(self):
        doc = canvas(shape("n1", "长" * 300))
        self.assertEqual(len(extract_nodes(doc)[0]["label"]), 200)

    def test_extract_nodes_without_order_uses_shape_keys(self):
        doc = {"shapes": {"a": {"id": "a", "type": "shape", "text": "A"}}}
        self.assertEqual(extract_nodes(doc)[0]["node_key"], "a")

    def test_sync_diagram_nodes_preserves_followup_and_prunes(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="任务")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "旧"), shape("n2", "旧二")))
        self.api("POST", f"/api/diagrams/{diagram['id']}/nodes/n1/followup", {"task_id": task["id"]})
        self.api("PATCH", f"/api/diagrams/{diagram['id']}/nodes/n1", {"note": "备注"})

        count = sync_diagram_nodes(
            diagram["id"], canvas(shape("n1", "新标签"), shape("n3", "新增"))
        )
        self.assertEqual(count, 2)

        rows = {
            r["node_key"]: r
            for r in get_db().execute(
                "SELECT * FROM diagram_nodes WHERE diagram_id=?", (diagram["id"],)
            )
        }
        self.assertEqual(set(rows), {"n1", "n3"})
        self.assertEqual(rows["n1"]["label"], "新标签")
        self.assertEqual(rows["n1"]["followup_status"], "todo")  # preserved
        self.assertEqual(rows["n1"]["note"], "备注")  # preserved
        self.assertEqual(rows["n3"]["followup_status"], "none")
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) AS n FROM node_task_links WHERE node_key='n2'"
            ).fetchone()["n"],
            0,
        )

    def test_merge_followup_into_content_ignores_connectors(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="任务")
        diagram = self.new_diagram(
            project["id"], canvas(shape("n1", "节点"), shape("e1", "线", type="connector"))
        )
        self.api("POST", f"/api/diagrams/{diagram['id']}/nodes/n1/followup", {"task_id": task["id"]})

        content = merge_followup_into_content(diagram["id"], canvas(shape("n1", "节点"), shape("e1", "线", type="connector")))
        self.assertEqual(content["shapes"]["n1"]["tt"]["tasks"][0]["title"], "任务")
        self.assertTrue(content["shapes"]["n1"]["tt"]["tasks"][0]["primary"])
        self.assertNotIn("tt", content["shapes"]["e1"])

    def test_content_of_handles_missing_json(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"])
        row = get_db().execute("SELECT * FROM diagrams WHERE id=?", (diagram["id"],)).fetchone()
        self.assertIn("shapes", content_of(row))

        get_db().execute("UPDATE diagrams SET content_json='not json' WHERE id=?", (diagram["id"],))
        row = get_db().execute("SELECT * FROM diagrams WHERE id=?", (diagram["id"],)).fetchone()
        self.assertEqual(content_of(row)["version"], 2)


class TaskServiceTest(ApiTestCase):
    def test_project_stats_progress(self):
        project = self.new_project()
        self.assertEqual(project_stats(project["id"])["task_progress"], 0)
        self.new_task(project["id"], title="a", status="done")
        self.new_task(project["id"], title="b", status="doing")
        self.new_task(project["id"], title="c", status="todo")
        stats = project_stats(project["id"])
        self.assertEqual(stats["task_total"], 3)
        self.assertEqual(stats["task_done"], 1)
        self.assertEqual(stats["task_doing"], 1)
        self.assertEqual(stats["task_open"], 2)
        self.assertEqual(stats["task_progress"], 33)

    def test_create_task_record_accepts_explicit_id_and_float_order(self):
        project = self.new_project()
        task_id = create_task_record(
            project["id"],
            {"id": "t_imported_1", "title": "导入任务", "sort_order": "2.5"},
            source="import",
        )
        self.assertEqual(task_id, "t_imported_1")
        row = get_db().execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        self.assertEqual(row["sort_order"], 2.5)
        self.assertEqual(row["source"], "import")

        # Invalid sort order falls back to 0 instead of crashing.
        other = create_task_record(project["id"], {"title": "bad order", "sort_order": "abc"})
        self.assertEqual(
            get_db().execute("SELECT sort_order FROM tasks WHERE id=?", (other,)).fetchone()[0],
            0.0,
        )

    def test_todo_state_shape(self):
        project = self.new_project(name="状态项目", stage="bidding")
        task = self.new_task(project["id"], title="任务", tags=["T"], due_date="2026-05-01T10:00:00")
        state = todo_state(project["id"])
        self.assertEqual(state["version"], "2.0")
        self.assertEqual(state["topotash"]["projectName"], "状态项目")
        self.assertEqual(state["topotash"]["stage"], "bidding")
        self.assertEqual(state["topotash"]["stageLabel"], "招投标")
        self.assertEqual(len(state["tasks"]), 1)
        item = state["tasks"][0]
        self.assertEqual(item["id"], task["id"])
        self.assertEqual(item["dueDate"], "2026-05-01T10:00:00")
        self.assertEqual(item["projectId"], task["category_id"])
        self.assertEqual(item["tags"], ["T"])
        self.assertIn("aiConfig", state)
        self.assertIn("aiChatHistory", state)
