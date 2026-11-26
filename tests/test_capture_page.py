"""速记页面、浮窗控制端点，以及「速记 = 建任务」的接口契约。"""
from __future__ import annotations

from tests.support import ApiTestCase


class CapturePageTest(ApiTestCase):
    def test_capture_page_renders(self):
        response = self.client.get("/capture")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("TopoTash 速记", html)
        self.assertIn("capture.js", html)
        # 速记记的是任务：不再有「最近记录」区块
        self.assertNotIn("最近记录", html)

    def test_healthz_reports_database(self):
        data = self.get_json("/healthz")
        self.assertTrue(data["ok"])
        self.assertTrue(data["database"])

    def test_window_action_without_shell_window(self):
        # 浏览器模式没有原生窗口：这些动作都应 404，而不是 500
        for action in ("collapse", "expand", "move", "close"):
            data = self.api("POST", "/api/capture/window", {"action": action}, status=404)
            self.assertEqual(data["error"], "window_not_found")

    def test_window_action_unknown(self):
        data = self.api("POST", "/api/capture/window", {"action": "nope"}, status=400)
        self.assertEqual(data["error"], "unknown_action")

    def test_capture_state_defaults(self):
        data = self.get_json("/api/capture/state")
        self.assertTrue(data["shell"])
        self.assertFalse(data["collapsed"])


class CaptureTaskFlowTest(ApiTestCase):
    """速记写的是任务（title + 售前阶段），不是「进展」。"""

    def setUp(self):
        super().setUp()
        self.project = self.new_project(name="云平台 POC", stage="proposal")

    def test_task_keeps_explicit_stage(self):
        task = self.api(
            "POST",
            "/api/tasks",
            {"project_id": self.project["id"], "title": "确认 POC 环境", "stage": "poc", "source": "floating"},
            201,
        )
        self.assertEqual(task["stage"], "poc")
        self.assertEqual(task["stage_label"], "POC 验证")
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["source"], "floating")

    def test_task_falls_back_to_project_stage(self):
        task = self.api(
            "POST",
            "/api/tasks",
            {"project_id": self.project["id"], "title": "输出方案 V1", "source": "floating"},
            201,
        )
        self.assertEqual(task["stage"], "proposal")

    def test_task_appears_in_project_list_and_can_be_deleted(self):
        task = self.api(
            "POST",
            "/api/tasks",
            {"project_id": self.project["id"], "title": "约评审会", "stage": "bidding"},
            201,
        )
        items = self.get_json(f"/api/tasks?project_id={self.project['id']}")["items"]
        self.assertEqual([t["title"] for t in items], ["约评审会"])

        self.api("DELETE", f"/api/tasks/{task['id']}")
        self.assertEqual(self.get_json(f"/api/tasks?project_id={self.project['id']}")["items"], [])

    def test_project_page_has_no_updates_tab(self):
        response = self.client.get(f"/projects/{self.project['id']}")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('data-tab="updates"', html)
        self.assertNotIn('id="panel-updates"', html)
