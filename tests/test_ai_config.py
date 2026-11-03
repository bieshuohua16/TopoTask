"""AI configuration, draft lifecycle and tool-loop tests (model calls are stubbed)."""
from __future__ import annotations

import json
from unittest import mock

from db import get_db
from services_ai import (
    _datetime_local,
    _parse_starter_tasks,
    _parse_tags,
    _priority_value,
    _stage_key,
    _status_key,
    _task_status_key,
    apply_action,
    execute_tool,
    public_ai_config,
    run_chat,
    save_ai_config,
    test_ai_connection,
)
from tests.support import ApiTestCase
from tests.test_ai import text_reply, tool_call


class AIConfigTest(ApiTestCase):
    def test_defaults_are_unconfigured(self):
        data = self.get_json("/api/ai/config")
        self.assertFalse(data["configured"])
        self.assertFalse(data["api_key_set"])
        self.assertEqual(data["api_key_hint"], "")
        self.assertTrue(any(p["key"] == "deepseek" for p in data["presets"]))

    def test_save_validation(self):
        base = self.client.put("/api/ai/config", json={"model": "m", "api_key": "k"})
        self.assertEqual(base.status_code, 400)
        self.assertEqual(base.get_json()["error"]["code"], "ai_base_required")

        model = self.client.put("/api/ai/config", json={"api_base": "https://x/v1", "api_key": "k"})
        self.assertEqual(model.status_code, 400)
        self.assertEqual(model.get_json()["error"]["code"], "ai_model_required")

        key = self.client.put(
            "/api/ai/config", json={"api_base": "https://x/v1", "model": "m"}
        )
        self.assertEqual(key.status_code, 400)
        self.assertEqual(key.get_json()["error"]["code"], "ai_key_required")

        local = self.client.put(
            "/api/ai/config", json={"api_base": "http://127.0.0.1:11434/v1", "model": "qwen2.5"}
        )
        self.assertEqual(local.status_code, 200)
        self.assertTrue(local.get_json()["configured"])

    def test_api_base_is_normalised(self):
        saved = self.api(
            "PUT",
            "/api/ai/config",
            {
                "api_base": "https://api.deepseek.com/v1/chat/completions/",
                "model": "deepseek-chat",
                "api_key": "sk-test-key-1234",
            },
        )
        self.assertEqual(saved["api_base"], "https://api.deepseek.com/v1")
        self.assertEqual(saved["api_key_hint"], "••••1234")
        self.assertTrue(saved["api_key_set"])
        self.assertTrue(saved["configured"])
        self.assertNotIn("sk-test-key-1234", json.dumps(saved))

    def test_key_is_preserved_and_can_be_cleared(self):
        self.api(
            "PUT",
            "/api/ai/config",
            {"api_base": "https://x/v1", "model": "m", "api_key": "sk-test-key-1234"},
        )
        # Saving other fields without sending the key must not wipe it.
        updated = self.api(
            "PUT", "/api/ai/config", {"api_base": "https://x/v1", "model": "m2"}
        )
        self.assertTrue(updated["api_key_set"])
        self.assertEqual(updated["model"], "m2")

        cleared = self.api(
            "PUT",
            "/api/ai/config",
            {"api_base": "http://127.0.0.1:11434/v1", "model": "m2", "clear_key": True},
        )
        self.assertFalse(cleared["api_key_set"])
        self.assertTrue(cleared["configured"])  # local providers do not need a key

        # Clearing the key of a remote provider would leave an unusable config.
        remote = self.client.put(
            "/api/ai/config",
            json={"api_base": "https://x/v1", "model": "m2", "clear_key": True},
        )
        self.assertEqual(remote.status_code, 400)
        self.assertEqual(remote.get_json()["error"]["code"], "ai_key_required")

    def test_temperature_is_clamped(self):
        cfg = save_ai_config(
            {"api_base": "https://x/v1", "model": "m", "api_key": "k", "temperature": 9}
        )
        self.assertEqual(cfg["temperature"], 2.0)
        cfg = save_ai_config(
            {"api_base": "https://x/v1", "model": "m", "api_key": "k", "temperature": "bad"}
        )
        self.assertEqual(cfg["temperature"], 0.7)
        self.assertEqual(public_ai_config()["temperature"], 0.7)

    def test_test_connection_ok_and_error(self):
        save_ai_config(
            {"api_base": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key": "k"}
        )
        with mock.patch(
            "services_ai.chat_completion",
            return_value={"model": "deepseek-chat", "choices": [{"message": {"content": "OK"}}]},
        ):
            result = test_ai_connection()
        self.assertTrue(result["ok"])
        self.assertEqual(result["reply"], "OK")
        self.assertEqual(result["model"], "deepseek-chat")

        from db import ApiError

        with mock.patch(
            "services_ai.chat_completion", side_effect=ApiError("API Key 无效或已过期（401）。", 401)
        ):
            failed = test_ai_connection()
        self.assertFalse(failed["ok"])
        self.assertIn("401", failed["error"])

        # HTTP wrapper accepts the form-shaped draft.
        with mock.patch(
            "services_ai.chat_completion",
            return_value={"choices": [{"message": {"content": "OK"}}]},
        ):
            response = self.client.post(
                "/api/ai/test",
                json={"draft": {"api_base": "https://x/v1", "model": "m", "api_key": "k"}},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_need_config_when_unconfigured(self):
        result = run_chat(None, "你好", {})
        self.assertFalse(result["ok"])
        self.assertTrue(result["need_config"])
        self.assertEqual(result["messages"], [])
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM ai_conversations").fetchone()["n"], 0
        )


class AIHelperTest(ApiTestCase):
    def test_alias_normalisation(self):
        self.assertEqual(_stage_key("POC 验证"), "poc")
        self.assertEqual(_stage_key("POC"), "poc")
        self.assertEqual(_stage_key("需求调研"), "research")
        self.assertEqual(_stage_key("unknown", "bidding"), "bidding")
        self.assertEqual(_status_key("已赢单"), "won")
        self.assertEqual(_status_key("进行中"), "active")
        self.assertEqual(_task_status_key("已完成"), "done")
        self.assertEqual(_task_status_key("未开始"), "todo")
        self.assertEqual(_priority_value("P0 紧急"), 0)
        self.assertEqual(_priority_value("p2"), 2)
        self.assertEqual(_priority_value("9"), 3)
        self.assertEqual(_priority_value("nope", 1), 1)
        self.assertEqual(_datetime_local("2026-01-02 03:04:05"), "2026-01-02T03:04")
        self.assertEqual(_datetime_local("2026-01-02"), "2026-01-02T00:00")
        self.assertEqual(_datetime_local(""), "")

    def test_local_endpoint_detection(self):
        from services_ai import _is_local_api

        self.assertTrue(_is_local_api("http://127.0.0.1:11434/v1"))
        self.assertTrue(_is_local_api("http://localhost:11434/v1"))
        self.assertTrue(_is_local_api("http://[::1]:11434/v1"))
        self.assertFalse(_is_local_api("https://api.deepseek.com/v1"))
        # A remote host that merely contains the word "localhost" is not local.
        self.assertFalse(_is_local_api("https://notlocalhost.example.com/v1"))
        self.assertFalse(_is_local_api(""))

    def test_parse_tags_and_starter_tasks(self):
        self.assertEqual(_parse_tags("a, b，c；d\n a"), ["a", "b", "c", "d"])
        self.assertEqual(_parse_tags(["x", " x ", ""]), ["x"])

        items = _parse_starter_tasks("需求调研 | 访谈客户\nPOC 验证 | 环境确认\n自由任务")
        self.assertEqual(
            [i["stage"] for i in items], ["research", "poc", None]
        )
        self.assertEqual(items[1]["title"], "环境确认")
        self.assertEqual(
            _parse_starter_tasks([{"title": "A", "stage": "poc"}, "B"]),
            [{"title": "A", "stage": "poc"}, {"title": "B", "stage": None}],
        )


class AIToolTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        save_ai_config(
            {"api_base": "http://127.0.0.1:9/v1", "api_key": "sk-test-key-1234", "model": "fake"}
        )
        self.project = self.new_project(name="星海银行 POC", customer="星海银行", stage="poc")
        self.task = self.new_task(self.project["id"], title="确认环境", status="todo")

    def test_read_tools(self):
        result = execute_tool("list_projects", {"q": "星海"}, "cv_test", {})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["projects"][0]["id"], self.project["id"])

        detail = execute_tool("get_project", {"project_ref": self.project["id"]}, "cv_test", {})
        self.assertEqual(detail["project"]["id"], self.project["id"])
        self.assertEqual(len(detail["open_tasks"]), 1)

        tasks = execute_tool("list_tasks", {"project_ref": self.project["id"]}, "cv_test", {})
        self.assertEqual(tasks["count"], 1)

        task = execute_tool("get_task", {"task_ref": self.task["id"]}, "cv_test", {})
        self.assertEqual(task["task"]["title"], "确认环境")

        summary = execute_tool("portfolio_summary", {}, "cv_test", {})
        self.assertEqual(summary["projects_total"], 1)
        self.assertEqual(summary["tasks_total"], 1)

        search = execute_tool("search", {"q": "星海"}, "cv_test", {})
        self.assertEqual(len(search["projects"]), 1)

    def test_resolve_errors(self):
        from db import ApiError

        with self.assertRaises(ApiError) as ctx:
            execute_tool("get_project", {"project_ref": "不存在的项目"}, "cv_test", {})
        self.assertEqual(ctx.exception.status, 404)

        self.new_project(name="星海银行 POC 二", customer="星海银行")
        with self.assertRaises(ApiError) as ctx:
            execute_tool("get_project", {"project_ref": "星海"}, "cv_test", {})
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(ctx.exception.code, "project_ambiguous")

        self.assertEqual(
            execute_tool("unknown_tool", {}, "cv_test", {}),
            {"ok": False, "error": "未知工具：unknown_tool"},
        )

    def test_create_project_draft_needs_a_name(self):
        result = execute_tool("create_project", {}, "cv_test", {})
        self.assertFalse(result["ok"])
        self.assertIn("项目名称", result["error"])
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM ai_actions").fetchone()["n"], 0
        )

    def test_update_draft_without_changes_is_rejected(self):
        result = execute_tool(
            "update_project", {"project_ref": self.project["id"], "owner": ""}, "cv_test", {}
        )
        # owner is currently empty, so there is nothing to change.
        self.assertFalse(result["ok"])
        self.assertIn("没有检测到需要修改", result["error"])

    def test_cancel_action_flow(self):
        cases = [
            tool_call("create_task", {"project_ref": self.project["id"], "title": "取消我"}),
            text_reply("草稿已生成。"),
        ]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            chat = self.client.post(
                "/api/ai/chat",
                json={"message": "加个任务", "context": {"project_id": self.project["id"]}},
            ).get_json()
        action = chat["actions"][0]

        cancelled = self.client.post(f"/api/ai/actions/{action['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["action"]["status"], "cancelled")

        again = self.client.post(f"/api/ai/actions/{action['id']}/cancel")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.get_json()["error"]["code"], "action_already_handled")

        confirmed = self.client.post(f"/api/ai/actions/{action['id']}/confirm", json={})
        self.assertEqual(confirmed.status_code, 409)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"], 1
        )

        missing = self.client.post("/api/ai/actions/a_missing/cancel")
        self.assertEqual(missing.status_code, 404)

    def test_delete_task_draft(self):
        cases = [
            tool_call("delete_task", {"task_ref": self.task["id"]}),
            text_reply("请确认删除。"),
        ]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            chat = self.client.post(
                "/api/ai/chat", json={"message": "删掉这个任务", "context": {}}
            ).get_json()
        action = chat["actions"][0]
        self.assertEqual(action["kind"], "delete_task")
        self.assertIn("不可恢复", action["warning"])

        self.client.post(f"/api/ai/actions/{action['id']}/confirm", json={})
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"], 0
        )

    def test_tool_loop_is_bounded(self):
        calls = [tool_call("portfolio_summary", {}, f"call_{i}") for i in range(6)]
        with mock.patch("services_ai.chat_completion", side_effect=calls):
            result = run_chat(None, "一直查询", {})
        self.assertTrue(result["ok"])
        self.assertTrue(any("工具调用次数过多" in m["content"] for m in result["messages"]))
        detail = self.get_json(f"/api/ai/conversations/{result['conversation']['id']}")
        self.assertTrue(any("工具调用次数过多" in m["content"] for m in detail["messages"]))

    def test_conversation_delete_cascades(self):
        cases = [text_reply("你好，有什么可以帮你？")]
        with mock.patch("services_ai.chat_completion", side_effect=cases):
            chat = self.client.post("/api/ai/chat", json={"message": "在吗"}).get_json()
        conversation_id = chat["conversation"]["id"]

        deleted = self.api("DELETE", f"/api/ai/conversations/{conversation_id}")
        self.assertTrue(deleted["deleted"])
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM ai_messages").fetchone()["n"], 0
        )
        self.assertEqual(self.client.get(f"/api/ai/conversations/{conversation_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/ai/conversations/{conversation_id}").status_code, 404)

    def test_conversation_can_be_created_explicitly(self):
        created = self.api("POST", "/api/ai/conversations", {"project_id": self.project["id"]}, status=201)
        self.assertEqual(created["project_id"], self.project["id"])
        detail = self.get_json(f"/api/ai/conversations/{created['id']}")
        self.assertEqual(detail["messages"], [])
        self.assertEqual(detail["actions"], [])

    def test_chat_requires_a_message(self):
        response = self.client.post("/api/ai/chat", json={"message": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "message_required")

    def test_system_prompt_includes_context_and_custom_prompt(self):
        from services_ai import build_system_prompt

        prompt = build_system_prompt({"project_id": self.project["id"], "page": "project"})
        self.assertIn("星海银行 POC", prompt)
        self.assertIn("用户当前打开的项目", prompt)
        self.assertIn("project", prompt)

        save_ai_config({"system_prompt": "回答尽量简短"})
        prompt = build_system_prompt({})
        self.assertIn("回答尽量简短", prompt)

    def test_apply_action_unknown_kind_is_rejected(self):
        from db import ApiError

        db = get_db()
        db.execute(
            """INSERT INTO ai_conversations(id, title, created_at, updated_at)
               VALUES ('cv_x', 'x', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"""
        )
        db.execute(
            """INSERT INTO ai_actions(id, conversation_id, kind, payload, status, result, created_at)
               VALUES ('a_x', 'cv_x', 'wat', '{}', 'pending', '{}', '2026-01-01T00:00:00Z')"""
        )
        db.commit()
        with self.assertRaises(ApiError) as ctx:
            apply_action("a_x")
        self.assertEqual(ctx.exception.code, "unknown_action_kind")
        # The failure rolls the claim back, so the draft stays pending.
        self.assertEqual(
            db.execute("SELECT status FROM ai_actions WHERE id='a_x'").fetchone()["status"],
            "pending",
        )
