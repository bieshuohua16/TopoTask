"""AI assistant tests (no network: the model client is stubbed)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_TMP_DIR = Path(os.environ.get("TEMP") or tempfile.gettempdir())
os.environ["TOPOTASH_DB"] = str(_TMP_DIR / ("tt_ai_bootstrap_%s.db" % os.getpid()))

from app import create_app  # noqa: E402


def tool_call(name: str, arguments: dict, call_id: str = "call_1") -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                }
            }
        ]
    }


def text_reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def tearDownModule():
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(os.environ["TOPOTASH_DB"] + suffix).unlink()
        except FileNotFoundError:
            pass


class AITestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = str(
            _TMP_DIR / ("tt_ai_%s_%s.db" % (os.getpid(), self._testMethodName))
        )
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

        from services_ai import save_ai_config

        save_ai_config(
            {
                "api_base": "http://127.0.0.1:9/v1",
                "api_key": "sk-test-secret-1234",
                "model": "fake-model",
            }
        )

    def tearDown(self):
        self.ctx.pop()
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(self.db_path + suffix).unlink()
            except FileNotFoundError:
                pass

    def test_config_never_returns_raw_key(self):
        from services_ai import public_ai_config

        public = public_ai_config()
        self.assertTrue(public["configured"])
        self.assertTrue(public["api_key_set"])
        self.assertNotIn("sk-test-secret-1234", json.dumps(public, ensure_ascii=False))
        self.assertIn("1234", public["api_key_hint"])

    def test_draft_then_confirm_creates_project_and_tasks(self):
        from services_ai import apply_action, run_chat

        cases = [
            tool_call(
                "create_project",
                {
                    "name": "测试银行私有云 POC",
                    "customer": "测试银行",
                    "owner": "李娜",
                    "stage": "poc",
                    "starter_tasks": [
                        {"title": "确认 POC 环境", "stage": "poc"},
                        {"title": "输出测试报告", "stage": "poc"},
                    ],
                },
            ),
            text_reply("已生成草稿，请在右侧确认。"),
        ]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            result = run_chat(None, "帮我建一个测试银行的 POC 项目", {})

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["actions"]), 1)
        action = result["actions"][0]
        self.assertEqual(action["kind"], "create_project")
        self.assertEqual(action["status"], "pending")
        self.assertIn("name", [field["key"] for field in action["form"]])

        from db import get_db

        # Merely drafting a project must not write it.
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"], 0
        )

        applied = apply_action(action["id"], {"name": "测试银行私有云 POC"})
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["result"]["task_count"], 2)

        project = get_db().execute(
            "SELECT * FROM projects WHERE name=?", ("测试银行私有云 POC",)
        ).fetchone()
        self.assertIsNotNone(project)
        self.assertEqual(project["stage"], "poc")
        tasks = get_db().execute(
            "SELECT * FROM tasks WHERE project_id=? ORDER BY title", (project["id"],)
        ).fetchall()
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(task["source"] == "ai" for task in tasks))

        # A draft can only be applied once.
        from db import ApiError

        with self.assertRaises(ApiError):
            apply_action(action["id"])

    def test_read_tool_and_portfolio_summary(self):
        from services_ai import execute_tool

        result = execute_tool("list_projects", {}, "cv_test", {})
        self.assertIn("projects", result)
        self.assertEqual(result["count"], 0)

        summary = execute_tool("portfolio_summary", {}, "cv_test", {})
        self.assertEqual(summary["projects_total"], 0)
        self.assertEqual(summary["tasks_total"], 0)

    def test_starter_task_stage_accepts_labels(self):
        from services_ai import _parse_starter_tasks

        items = _parse_starter_tasks(
            "需求调研 | 客户访谈\nPOC 验证 | 环境确认\n方案编写 | 输出建议书\n自由任务"
        )
        self.assertEqual(
            [item["stage"] for item in items],
            ["research", "poc", "proposal", None],
        )
        self.assertEqual(items[1]["title"], "环境确认")

    def test_http_flow_draft_then_confirm(self):
        cases = [
            tool_call(
                "create_task",
                {"project_ref": "p_missing", "title": "不会创建"},
            ),
            text_reply("项目不存在，请先选择项目。"),
        ]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            response = self.client.post(
                "/api/ai/chat",
                json={"message": "给不存在的项目加任务", "context": {}},
            )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(any(m["role"] == "tool" for m in data["messages"]))

    def test_create_project_through_http_and_confirm(self):
        cases = [
            tool_call("create_project", {"name": "HTTP 项目", "customer": "客户 A"}),
            text_reply("请确认草稿。"),
        ]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            chat = self.client.post(
                "/api/ai/chat",
                json={"message": "新建 HTTP 项目", "context": {}},
            ).get_json()
        self.assertTrue(chat["ok"])
        action = chat["actions"][0]
        confirm = self.client.post(
            "/api/ai/actions/%s/confirm" % action["id"],
            json={"values": {"name": "HTTP 项目", "customer": "客户 A", "stage": "research"}},
        )
        self.assertEqual(confirm.status_code, 200)
        result = confirm.get_json()["action"]
        self.assertEqual(result["status"], "applied")

        listing = self.client.get("/api/projects").get_json()
        self.assertTrue(any(item["name"] == "HTTP 项目" for item in listing["items"]))

    def test_update_project_and_task_drafts(self):
        project = self.client.post(
            "/api/projects", json={"name": "待更新项目", "stage": "research"}
        ).get_json()
        project_id = project["id"]
        task = self.client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "待更新任务", "priority": 2},
        ).get_json()
        task_id = task["id"]

        cases = [
            tool_call(
                "update_project",
                {"project_ref": project_id, "stage": "poc", "owner": "王强"},
            ),
            tool_call(
                "update_task",
                {"task_ref": task_id, "status": "doing", "priority": 1},
            ),
            text_reply("两处修改都已生成草稿。"),
        ]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            chat = self.client.post(
                "/api/ai/chat",
                json={"message": "更新项目和任务", "context": {"project_id": project_id}},
            ).get_json()
        self.assertTrue(chat["ok"])
        self.assertEqual(len(chat["actions"]), 2)
        for action in chat["actions"]:
            response = self.client.post(
                "/api/ai/actions/%s/confirm" % action["id"], json={}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["action"]["status"], "applied")

        project_after = self.client.get(
            "/api/projects/%s" % project_id
        ).get_json()
        self.assertEqual(project_after["stage"], "poc")
        self.assertEqual(project_after["owner"], "王强")
        task_after = self.client.get("/api/tasks/%s" % task_id).get_json()
        self.assertEqual(task_after["status"], "doing")
        self.assertEqual(task_after["priority"], 1)

    def test_project_crud_and_legacy_config_not_exposed(self):
        created = self.client.post(
            "/api/projects",
            json={"name": "CRUD 项目", "customer": "客户 B", "stage": "research"},
        ).get_json()
        project_id = created["id"]

        state = self.client.get(
            "/api/projects/%s/todo-state" % project_id
        ).get_json()
        state["aiConfig"] = {
            "apiBase": "https://legacy.example/v1",
            "apiKey": "sk-legacy-secret",
            "model": "legacy-model",
        }
        self.client.put(
            "/api/projects/%s/todo-state" % project_id, json=state
        )

        listing = self.client.get("/api/projects").get_json()
        item = next(p for p in listing["items"] if p["id"] == project_id)
        self.assertNotIn("todo_config", item)
        self.assertNotIn("sk-legacy-secret", json.dumps(listing, ensure_ascii=False))

        patched = self.client.patch(
            "/api/projects/%s" % project_id, json={"stage": "poc", "owner": "张伟"}
        ).get_json()
        self.assertEqual(patched["stage"], "poc")
        self.assertEqual(patched["owner"], "张伟")

        deleted = self.client.delete(
            "/api/projects/%s" % project_id
        ).get_json()
        self.assertTrue(deleted["deleted"])
        self.assertEqual(
            self.client.get("/api/projects/%s" % project_id).status_code, 404
        )

    def test_conversation_persistence_and_history(self):
        from services_ai import get_conversation_detail, run_chat

        cases = [
            tool_call("list_projects", {}),
            text_reply("目前还没有项目。"),
        ]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            result = run_chat(None, "现在有哪些项目？", {"page": "dashboard"})

        conversation_id = result["conversation"]["id"]
        detail = get_conversation_detail(conversation_id)
        self.assertEqual(detail["conversation"]["id"], conversation_id)
        self.assertTrue(any(m["role"] == "user" for m in detail["messages"]))
        self.assertTrue(any(m["role"] == "assistant" for m in detail["messages"]))
        self.assertEqual(detail["conversation"]["title"], "现在有哪些项目？")

        history = self.client.get("/api/ai/conversations").get_json()["items"]
        self.assertTrue(any(item["id"] == conversation_id for item in history))


if __name__ == "__main__":
    unittest.main()
