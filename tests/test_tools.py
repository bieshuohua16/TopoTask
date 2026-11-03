"""Tests for the demo seeder, the legacy JSON importer and the Flask CLI."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from db import get_db
from tests.support import ApiTestCase, canvas, shape, TMP_DIR
from tools.migrate_json import _import_todo, _import_visio, _visio_files
from tools.seed_demo import seed_demo


class SeedDemoTest(ApiTestCase):
    def test_seed_creates_portfolio_once(self):
        created = seed_demo()
        self.assertEqual(created, 4)

        db = get_db()
        self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"], 4)
        self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM diagrams").fetchone()["n"], 4)
        self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"], 23)
        self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM node_task_links").fetchone()["n"], 5)
        self.assertEqual(
            db.execute(
                "SELECT COUNT(*) AS n FROM diagram_nodes WHERE followup_status IN ('todo','doing')"
            ).fetchone()["n"],
            5,
        )

        overview = self.get_json("/api/views/overview")
        self.assertEqual(overview["project_total"], 4)
        self.assertEqual(overview["task_total"], 23)
        self.assertEqual(overview["diagram_total"], 4)
        self.assertEqual(overview["followup_total"], 5)

        # Seeding again is a no-op.
        self.assertEqual(seed_demo(), 0)
        self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"], 4)

    def test_flask_cli_commands(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("initialized database", result.output)

        result = runner.invoke(args=["seed-demo"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("seeded 4 projects", result.output)


def sample_todo() -> dict:
    return {
        "version": "2.0",
        "projects": [
            {"id": "c_impl", "name": "实施", "color": "#111111"},
            {"id": "c_presale", "name": "售前", "color": "#222222"},
        ],
        "tags": ["池标签"],
        "tasks": [
            {
                "id": "t_old_1",
                "title": "老任务一",
                "projectId": "c_impl",
                "status": "doing",
                "priority": 0,
                "dueDate": "2026-01-02T03:04:00",
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-02T00:00:00Z",
                "tags": ["重点"],
                "subtasks": [{"id": "st_old_1", "title": "子任务", "completed": True}],
                "order": 0,
            },
            {
                "id": "t_old_2",
                "title": "老任务二",
                "projectId": "c_presale",
                "stage": "poc",
                "priority": 2,
                "order": 0,
            },
        ],
        "aiConfig": {"apiBase": "https://legacy.example/v1", "apiKey": "sk-legacy", "model": "legacy"},
        "aiChatHistory": [{"role": "user", "content": "历史对话"}],
    }


class MigrateTodoTest(ApiTestCase):
    def test_import_todo_into_one_project(self):
        created, task_count, tag_count = _import_todo(
            get_db(), sample_todo(), "历史任务迁移", False, "research", False, ["池标签"]
        )
        self.assertEqual(task_count, 2)
        self.assertEqual(tag_count, 1)
        self.assertEqual(len(created), 1)
        project_id, name = created[0]
        self.assertEqual(name, "历史任务迁移")

        db = get_db()
        project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        self.assertEqual(project["todo_config"].count("sk-legacy"), 1)

        categories = db.execute(
            "SELECT * FROM task_categories WHERE project_id=? ORDER BY sort_order", (project_id,)
        ).fetchall()
        self.assertEqual([c["name"] for c in categories], ["实施", "售前"])

        task = db.execute("SELECT * FROM tasks WHERE id='t_old_1'").fetchone()
        self.assertEqual(task["project_id"], project_id)
        self.assertEqual(task["category_id"], categories[0]["id"])
        self.assertEqual(task["status"], "doing")
        self.assertEqual(task["priority"], 0)  # P0 must survive the import
        self.assertEqual(task["due_date"], "2026-01-02T03:04:00")
        self.assertEqual(task["created_at"], "2025-01-01T00:00:00Z")
        self.assertEqual(task["sort_order"], 0)
        self.assertEqual(task["source"], "import")

        second = db.execute("SELECT * FROM tasks WHERE id='t_old_2'").fetchone()
        self.assertEqual(second["stage"], "poc")
        self.assertEqual(second["category_id"], categories[1]["id"])
        self.assertEqual(second["sort_order"], 0)  # explicit order 0 is preserved
        subtask = db.execute("SELECT * FROM subtasks WHERE id='st_old_1'").fetchone()
        self.assertEqual(subtask["task_id"], "t_old_1")
        self.assertEqual(subtask["completed"], 1)

        tags = {
            r["name"]
            for r in db.execute(
                """SELECT tg.name FROM task_tags tt JOIN tags tg ON tg.id=tt.tag_id
                   WHERE tt.task_id='t_old_1'"""
            )
        }
        self.assertEqual(tags, {"重点"})
        pool = {r["name"] for r in db.execute("SELECT name FROM tags WHERE project_id=?", (project_id,))}
        self.assertEqual(pool, {"重点", "池标签"})

    def test_import_todo_split_projects(self):
        created, task_count, _ = _import_todo(
            get_db(), sample_todo(), "", True, "proposal", False, []
        )
        self.assertEqual(task_count, 2)
        self.assertEqual({name for _pid, name in created}, {"实施", "售前"})
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"], 2
        )
        # The legacy AI config is carried over only once, on the first project.
        configs = get_db().execute("SELECT todo_config FROM projects").fetchall()
        self.assertEqual(sum(1 for c in configs if "sk-legacy" in c["todo_config"]), 1)

    def test_import_todo_dry_run_writes_nothing(self):
        created, task_count, tag_count = _import_todo(
            get_db(), sample_todo(), "演练", False, "research", True, ["池标签"]
        )
        self.assertEqual(task_count, 2)
        self.assertEqual(tag_count, 1)
        self.assertEqual(created, [("dry", "演练")])
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"], 0
        )

    def test_import_unknown_category_falls_back_to_default(self):
        data = sample_todo()
        data["tasks"] = [{"id": "t_x", "title": "无分类", "projectId": "c_missing"}]
        created, _, _ = _import_todo(get_db(), data, "回退", False, "research", False, [])
        db = get_db()
        task = db.execute("SELECT * FROM tasks WHERE id='t_x'").fetchone()
        first = db.execute(
            "SELECT id FROM task_categories WHERE project_id=? ORDER BY sort_order", (created[0][0],)
        ).fetchone()
        self.assertEqual(task["category_id"], first["id"])


class MigrateVisioTest(ApiTestCase):
    def test_visio_files_discovery(self):
        folder = Path(tempfile.mkdtemp(dir=str(TMP_DIR)))
        try:
            (folder / "a.vweb.json").write_text(json.dumps(canvas(shape("n1", "A"))), encoding="utf-8")
            (folder / "b.json").write_text(json.dumps(canvas(shape("n2", "B"))), encoding="utf-8")
            (folder / "c.json").write_text("not json", encoding="utf-8")
            (folder / "d.json").write_text(json.dumps({"hello": "world"}), encoding="utf-8")

            files = _visio_files([str(folder)])
            self.assertEqual({f.name for f in files}, {"a.vweb.json", "b.json"})
            self.assertEqual(_visio_files([str(folder), str(folder)]), files)  # deduped
        finally:
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()

    def test_import_visio_creates_diagrams_and_dedupes_names(self):
        project = self.new_project()
        folder = Path(tempfile.mkdtemp(dir=str(TMP_DIR)))
        try:
            path = folder / "poc_env.vweb.json"
            path.write_text(
                json.dumps(canvas(shape("n1", "服务器"), shape("n2", "交换机"))), encoding="utf-8"
            )
            count = _import_visio(get_db(), [path], project["id"], False)
            self.assertEqual(count, 1)

            diagrams = get_db().execute(
                "SELECT * FROM diagrams WHERE project_id=?", (project["id"],)
            ).fetchall()
            self.assertEqual(len(diagrams), 1)
            self.assertEqual(diagrams[0]["name"], "poc env")
            self.assertEqual(diagrams[0]["node_count"], 2)
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) AS n FROM diagram_nodes").fetchone()["n"], 2
            )

            # Importing the same file again keeps a distinct, suffixed name.
            self.assertEqual(_import_visio(get_db(), [path], project["id"], False), 1)
            names = {
                r["name"]
                for r in get_db().execute("SELECT name FROM diagrams WHERE project_id=?", (project["id"],))
            }
            self.assertEqual(names, {"poc env", "poc env (导入)"})
        finally:
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()

    def test_import_visio_dry_run(self):
        project = self.new_project()
        folder = Path(tempfile.mkdtemp(dir=str(TMP_DIR)))
        try:
            path = folder / "x.json"
            path.write_text(json.dumps(canvas(shape("n1", "X"))), encoding="utf-8")
            self.assertEqual(_import_visio(get_db(), [path], project["id"], True), 1)
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) AS n FROM diagrams").fetchone()["n"], 0
            )
        finally:
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()


class MigrateCliTest(ApiTestCase):
    def test_cli_requires_input(self):
        from tools.migrate_json import main

        with mock.patch("sys.argv", ["migrate_json.py"]):
            self.assertEqual(main(), 2)

    def test_cli_imports_todo_file(self):
        from tools.migrate_json import main

        folder = Path(tempfile.mkdtemp(dir=str(TMP_DIR)))
        db_path = str(TMP_DIR / f"tt_cli_{self._testMethodName}.db")
        try:
            todo_path = folder / "todos.json"
            todo_path.write_text(json.dumps(sample_todo(), ensure_ascii=False), encoding="utf-8")
            argv = [
                "migrate_json.py",
                "--todo", str(todo_path),
                "--project-name", "CLI 项目",
                "--db", db_path,
                "--stage", "poc",
            ]
            with mock.patch("sys.argv", argv):
                self.assertEqual(main(), 0)

            import sqlite3

            conn = sqlite3.connect(db_path)
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 2)
                self.assertEqual(
                    conn.execute("SELECT stage FROM projects").fetchone()[0], "poc"
                )
            finally:
                conn.close()
        finally:
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()
            for suffix in ("", "-wal", "-shm"):
                Path(db_path + suffix).unlink(missing_ok=True)

    def test_cli_rejects_bad_todo_payload(self):
        from tools.migrate_json import main

        folder = Path(tempfile.mkdtemp(dir=str(TMP_DIR)))
        db_path = str(TMP_DIR / f"tt_cli_bad_{self._testMethodName}.db")
        try:
            bad = folder / "bad.json"
            bad.write_text(json.dumps({"nope": True}), encoding="utf-8")
            argv = ["migrate_json.py", "--todo", str(bad), "--db", db_path]
            with mock.patch("sys.argv", argv):
                self.assertEqual(main(), 1)
        finally:
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()
            for suffix in ("", "-wal", "-shm"):
                Path(db_path + suffix).unlink(missing_ok=True)
