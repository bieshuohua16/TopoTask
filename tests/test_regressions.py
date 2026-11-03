"""Regression coverage for data preservation, contention and list queries."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.support import ApiTestCase, canvas, shape
from tests.test_ai import text_reply, tool_call
from db import ApiError, get_db
from services_ai import apply_action, create_conversation, execute_tool, run_chat, save_ai_config


class DraftRegressionTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.new_project(name="Draft project", customer="Original customer")
        self.task = self.new_task(
            self.project["id"], title="Draft task", description="Original note",
            due_date="2026-11-10T09:00:00.123Z", tags=["original"],
        )
        self.conversation = create_conversation(self.project["id"])

    def draft(self, tool, **args):
        return execute_tool(tool, args, self.conversation["id"], {})["action"]

    def test_unrelated_task_edits_survive_confirmation(self):
        action = self.draft("update_task", task_ref=self.task["id"], priority=0)
        self.api("PATCH", f"/api/tasks/{self.task['id']}", {
            "description": "Manual note", "status": "doing", "tags": ["manual"],
        })
        # The browser submits all form values, including numeric strings.
        values = {k: str(v) for k, v in action["values"].items()}
        apply_action(action["id"], values)
        task = self.get_json(f"/api/tasks/{self.task['id']}")
        self.assertEqual(task["priority"], 0)
        self.assertEqual(task["description"], "Manual note")
        self.assertEqual(task["status"], "doing")
        self.assertEqual(task["tags"], ["manual"])
        self.assertEqual(task["due_date"], self.task["due_date"])

    def test_conflicting_task_edit_keeps_draft_pending(self):
        action = self.draft("update_task", task_ref=self.task["id"], priority=0)
        self.api("PATCH", f"/api/tasks/{self.task['id']}", {"priority": 1})
        response = self.client.post(f"/api/ai/actions/{action['id']}/confirm", json={})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "action_conflict")
        row = get_db().execute("SELECT status FROM ai_actions WHERE id=?", (action["id"],)).fetchone()
        self.assertEqual(row["status"], "pending")
        self.assertEqual(self.get_json(f"/api/tasks/{self.task['id']}")["priority"], 1)

    def test_project_draft_preserves_manual_edits_and_detects_conflicts(self):
        action = self.draft("update_project", project_ref=self.project["id"], stage="poc")
        self.api("PATCH", f"/api/projects/{self.project['id']}", {"customer": "Manual customer"})
        apply_action(action["id"], action["values"])
        current = self.get_json(f"/api/projects/{self.project['id']}")
        self.assertEqual(current["customer"], "Manual customer")
        self.assertEqual(current["stage"], "poc")
        conflict = self.draft("update_project", project_ref=self.project["id"], stage="bidding")
        self.api("PATCH", f"/api/projects/{self.project['id']}", {"stage": "proposal"})
        with self.assertRaises(ApiError) as caught:
            apply_action(conflict["id"])
        self.assertEqual(caught.exception.code, "action_conflict")

    def test_old_draft_requires_regeneration(self):
        action = self.draft("update_task", task_ref=self.task["id"], priority=0)
        row = get_db().execute("SELECT payload FROM ai_actions WHERE id=?", (action["id"],)).fetchone()
        payload = json.loads(row["payload"])
        payload.pop("baseline")
        get_db().execute("UPDATE ai_actions SET payload=? WHERE id=?", (json.dumps(payload), action["id"]))
        get_db().commit()
        with self.assertRaises(ApiError) as caught:
            apply_action(action["id"])
        self.assertEqual(caught.exception.code, "action_stale")

    def test_ai_deadline_keeps_timezone(self):
        action = self.draft(
            "create_task", project_ref=self.project["id"], title="Offset task",
            due_date="2026-11-10T17:00:00+08:00",
        )
        result = apply_action(action["id"])["result"]
        task = self.get_json(f"/api/tasks/{result['task_id']}")
        self.assertEqual(task["due_date"], "2026-11-10T09:00:00Z")

    def test_writes_remain_available_during_every_model_round(self):
        save_ai_config({"api_base": "http://localhost:11434/v1", "model": "stub"})
        replies = iter([
            tool_call("list_projects", {}),
            tool_call("create_task", {"project_ref": self.project["id"], "title": "Draft"}),
            text_reply("Ready"),
        ])

        def model(*_args, **_kwargs):
            with sqlite3.connect(self.db_path, timeout=0.05) as other:
                self.assertGreater(other.execute(
                    "SELECT COUNT(*) FROM ai_messages WHERE conversation_id=?",
                    (self.conversation["id"],),
                ).fetchone()[0], 0)
                other.execute("UPDATE projects SET owner='Concurrent writer' WHERE id=?", (self.project["id"],))
            return next(replies)

        with mock.patch("services_ai.chat_completion", side_effect=model) as client:
            result = run_chat(self.conversation["id"], "Make a draft", {})
        self.assertTrue(result["ok"])
        self.assertEqual(client.call_count, 3)
        self.assertEqual(len(result["actions"]), 1)


class NodeRegressionTest(ApiTestCase):
    def test_primary_removal_promotes_remaining_task_and_stays_in_sync(self):
        for method in ("delete_task", "unlink", "legacy_delete"):
            with self.subTest(method=method):
                project = self.new_project()
                diagram = self.new_diagram(project["id"], canvas(shape("n1")))
                first = self.new_task(project["id"])
                second = self.new_task(project["id"], status="doing")
                node_path = f"/api/diagrams/{diagram['id']}/nodes/n1"
                self.api("POST", node_path + "/followup", {"task_id": first["id"]})
                self.api("POST", node_path + "/links", {"task_id": second["id"]}, status=201)
                if method == "delete_task":
                    self.api("DELETE", f"/api/tasks/{first['id']}")
                elif method == "unlink":
                    self.api("DELETE", node_path + f"/links/{first['id']}")
                else:
                    state = self.get_json(f"/api/projects/{project['id']}/todo-state")
                    state["tasks"] = [t for t in state["tasks"] if t["id"] != first["id"]]
                    state["deleted_task_ids"] = [first["id"]]
                    self.api("PUT", f"/api/projects/{project['id']}/todo-state", state)
                node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
                self.assertEqual(node["primary_task"]["task_id"], second["id"])
                self.assertEqual(node["followup_status"], "doing")
                self.api("PATCH", f"/api/tasks/{second['id']}", {"status": "done"})
                node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
                self.assertEqual(node["followup_status"], "done")


class ValidationRegressionTest(ApiTestCase):
    def test_non_object_and_malformed_bodies_return_400(self):
        for path in ("/api/projects", "/api/tasks", "/api/diagrams", "/api/ai/chat"):
            for data in (["bad"], "bad", 42, None):
                with self.subTest(path=path, data=data):
                    response = self.client.post(path, data=json.dumps(data), content_type="application/json")
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json()["error"]["code"], "invalid_json")
            response = self.client.post(path, data="{", content_type="application/json")
            self.assertEqual(response.status_code, 400)

    def test_empty_project_name_and_invalid_task_fields(self):
        project = self.new_project()
        response = self.client.patch(f"/api/projects/{project['id']}", json={"name": " "})
        self.assertEqual(response.status_code, 400)
        for field, value in (
            ("tags", "POC"), ("tags", [42]), ("subtasks", "bad"),
            ("due_date", {}), ("due_date", "not-a-date"), ("title", []),
        ):
            with self.subTest(field=field, value=value):
                response = self.client.post("/api/tasks", json={
                    "project_id": project["id"], "title": "Task", field: value,
                })
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.get_json("/api/tasks")["total"], 0)


class QueryRegressionTest(ApiTestCase):
    def test_project_list_batches_stats_and_limits_followups_per_project(self):
        projects = [self.new_project() for _ in range(10)]
        task = self.new_task(projects[0]["id"], due_date="2027-01-01T09:00:00Z", status="doing")
        diagram = self.new_diagram(projects[0]["id"], canvas(*(shape(f"n{i}") for i in range(6))))
        get_db().execute("UPDATE diagram_nodes SET followup_status='todo' WHERE diagram_id=?", (diagram["id"],))
        get_db().commit()
        queries = []
        get_db().set_trace_callback(queries.append)
        try:
            listing = self.get_json("/api/projects")["items"]
        finally:
            get_db().set_trace_callback(None)
        selects = [q for q in queries if q.lstrip().upper().startswith("SELECT")]
        self.assertLessEqual(len(selects), 5)
        first = next(p for p in listing if p["id"] == projects[0]["id"])
        self.assertEqual(first["task_total"], 1)
        self.assertEqual(first["task_doing"], 1)
        self.assertEqual(first["next_due"], task["due_date"])
        self.assertEqual(first["followup_count"], 6)
        self.assertEqual(len(first["followup_nodes"]), 5)
        empty = next(p for p in listing if p["id"] == projects[1]["id"])
        self.assertEqual(empty["task_total"], 0)
        self.assertEqual(empty["task_progress"], 0)

    def test_diagram_list_omits_canvas_and_matches_detail_counts(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"], canvas(shape("n1")))
        task = self.new_task(project["id"])
        self.api("POST", f"/api/diagrams/{diagram['id']}/nodes/n1/followup", {"task_id": task["id"]})
        self.api("POST", f"/api/tasks/{task['id']}/diagrams", {"diagram_id": diagram["id"]}, status=201)
        detail = self.get_json(f"/api/diagrams/{diagram['id']}")
        queries = []
        get_db().set_trace_callback(queries.append)
        try:
            item = self.get_json("/api/diagrams")["items"][0]
        finally:
            get_db().set_trace_callback(None)
        self.assertNotIn("content_json", item)
        self.assertFalse(any("content_json" in q for q in queries))
        self.assertEqual(item["project_name"], project["name"])
        for key in ("node_count", "followup_count", "linked_task_count", "task_link_count"):
            self.assertEqual(item[key], detail[key])


class ShortcutRegressionTest(ApiTestCase):
    def test_launcher_only_reuses_the_requested_database(self):
        import start_topotash as launcher

        expected = str(Path(self.db_path).resolve())
        response = mock.MagicMock()
        with mock.patch.dict(os.environ):
            with mock.patch.object(launcher, "_port_open", return_value=True), mock.patch.object(
                launcher, "_wait_health", return_value=True,
            ), mock.patch.object(launcher._OPENER, "open", return_value=response), mock.patch.object(
                launcher, "_fail", return_value=1,
            ) as fail:
                response.__enter__.return_value.read.return_value = json.dumps({
                    "ok": True, "database": expected,
                }).encode()
                self.assertEqual(launcher.main(["--db", expected, "--no-browser"]), 0)
                fail.assert_not_called()
                response.__enter__.return_value.read.return_value = json.dumps({
                    "ok": True, "database": expected + ".other",
                }).encode()
                self.assertEqual(launcher.main(["--db", expected, "--no-browser"]), 1)
                fail.assert_called_once()

    def test_shortcut_carries_database_path(self):
        import setup_first_run as setup

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = str(root / "custom data.db")
            args = SimpleNamespace(icon=str(root / "icon.ico"), force_icon=False, desktop_dir=str(root))

            def create(link, **_kwargs):
                link.touch()

            with mock.patch.dict(os.environ, {"TOPOTASH_DB": database}):
                with mock.patch("tools.make_icon.ensure_icon"), mock.patch.object(
                    setup, "create_shortcut", side_effect=create,
                ) as shortcut:
                    setup.step_shortcut(args)
            self.assertEqual(
                shortcut.call_args.kwargs["arguments"],
                subprocess.list2cmdline([str(setup.ROOT / "start_topotash.py"), "--db", database]),
            )
