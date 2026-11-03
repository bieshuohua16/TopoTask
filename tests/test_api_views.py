"""Aggregated view endpoints, page routes and error handling."""
from __future__ import annotations

from tests.support import ApiTestCase, canvas, shape


class ViewApiTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.new_project(name="银行私有云", stage="poc")
        self.other = self.new_project(name="制造园区", stage="proposal", status="won")
        self.open_task = self.new_task(
            self.project["id"], title="环境部署", stage="poc", due_date="2020-01-01T09:00:00"
        )
        self.done_task = self.new_task(
            self.project["id"], title="方案评审", status="done", stage="proposal"
        )
        self.diagram = self.new_diagram(
            self.project["id"], canvas(shape("n1", "核心交换机")), name="POC 部署图"
        )
        self.api(
            "POST",
            f"/api/diagrams/{self.diagram['id']}/nodes/n1/followup",
            {"task_id": self.open_task["id"]},
        )
        self.api("POST", f"/api/tasks/{self.open_task['id']}/diagrams", {"diagram_id": self.diagram["id"]}, status=201)

    def test_overview_aggregates(self):
        data = self.get_json("/api/views/overview")
        self.assertEqual(data["project_total"], 2)
        self.assertEqual(data["active_projects"], 1)
        self.assertEqual(data["won_projects"], 1)
        self.assertEqual(data["task_total"], 2)
        self.assertEqual(data["task_done"], 1)
        self.assertEqual(data["task_open"], 1)
        self.assertEqual(data["task_overdue"], 1)
        self.assertEqual(data["diagram_total"], 1)
        self.assertEqual(data["followup_total"], 1)
        self.assertEqual(len(data["stage_stats"]), 4)
        poc = next(s for s in data["stage_stats"] if s["key"] == "poc")
        self.assertEqual(poc["project_count"], 1)
        self.assertEqual(poc["task_count"], 1)
        self.assertEqual(poc["open_task_count"], 1)
        self.assertEqual(len(data["upcoming"]), 1)
        self.assertEqual(data["upcoming"][0]["id"], self.open_task["id"])
        self.assertEqual(len(data["followups"]), 1)
        self.assertEqual(data["followups"][0]["label"], "核心交换机")
        self.assertEqual(data["followups"][0]["project_name"], "银行私有云")
        self.assertEqual(data["followups"][0]["tasks"][0]["id"], self.open_task["id"])

    def test_stage_board(self):
        board = self.get_json("/api/views/stage-board")
        self.assertFalse(board["include_done"])
        stages = {s["key"]: s for s in board["stages"]}
        self.assertEqual([t["id"] for t in stages["poc"]["tasks"]], [self.open_task["id"]])
        self.assertEqual(stages["proposal"]["tasks"], [])  # done tasks hidden by default

        with_done = self.get_json("/api/views/stage-board?include_done=1")
        proposal = next(s for s in with_done["stages"] if s["key"] == "proposal")
        self.assertEqual([t["id"] for t in proposal["tasks"]], [self.done_task["id"]])

        scoped = self.get_json(f"/api/views/stage-board?project_id={self.other['id']}")
        self.assertEqual(scoped["project_id"], self.other["id"])
        self.assertTrue(all(s["task_count"] == 0 for s in scoped["stages"]))

    def test_links_view(self):
        data = self.get_json(f"/api/views/links?project_id={self.project['id']}")
        self.assertEqual(len(data["diagrams"]), 1)
        diagram = data["diagrams"][0]
        self.assertEqual(diagram["name"], "POC 部署图")
        self.assertEqual(diagram["nodes"][0]["followup_status"], "todo")
        self.assertEqual(len(diagram["nodes"][0]["linked_tasks"]), 1)
        self.assertEqual(len(data["task_links"]), 1)
        self.assertEqual(data["task_links"][0]["title"], "环境部署")
        self.assertEqual(data["task_links"][0]["diagram_name"], "POC 部署图")
        self.assertEqual(data["task_links"][0]["project_name"], "银行私有云")

        empty = self.get_json(f"/api/views/links?project_id={self.other['id']}")
        self.assertEqual(empty["diagrams"], [])
        self.assertEqual(empty["task_links"], [])

    def test_search(self):
        empty = self.get_json("/api/views/search?q=")
        self.assertEqual(empty, {"projects": [], "tasks": [], "diagrams": []})

        data = self.get_json("/api/views/search?q=银行")
        self.assertEqual([p["id"] for p in data["projects"]], [self.project["id"]])

        by_task = self.get_json("/api/views/search?q=环境部署")
        self.assertEqual([t["id"] for t in by_task["tasks"]], [self.open_task["id"]])
        self.assertEqual(by_task["tasks"][0]["project_name"], "银行私有云")

        by_diagram = self.get_json("/api/views/search?q=部署图")
        self.assertEqual([d["id"] for d in by_diagram["diagrams"]], [self.diagram["id"]])

        nothing = self.get_json("/api/views/search?q=不存在的关键词")
        self.assertEqual(nothing["projects"], [])

    def test_healthz(self):
        data = self.get_json("/healthz")
        self.assertTrue(data["ok"])
        self.assertEqual(data["app"], "TopoTash")


class PageRoutesTest(ApiTestCase):
    def test_main_pages_render(self):
        project = self.new_project(name="页面项目")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")), name="页面拓扑图")

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        html = dashboard.get_data(as_text=True)
        self.assertIn("项目总览", html)
        self.assertIn("window.TT_CONFIG", html)
        self.assertIn("js/dashboard.js", html)

        self.assertIn("阶段看板", self.client.get("/board").get_data(as_text=True))
        library_html = self.client.get("/diagrams").get_data(as_text=True)
        self.assertIn("拓扑图库", library_html)
        self.assertIn("新建拓扑图", library_html)
        self.assertIn("导入拓扑图", library_html)
        self.assertIn("js/diagram-actions.js", library_html)

        project_page = self.client.get(f"/projects/{project['id']}")
        self.assertEqual(project_page.status_code, 200)
        project_html = project_page.get_data(as_text=True)
        self.assertIn("页面项目", project_html)
        self.assertIn("window.TT_PROJECT", project_html)
        self.assertIn("js/tasks.js", project_html)
        self.assertIn("导入拓扑图", project_html)
        self.assertIn("js/diagram-actions.js", project_html)

        editor = self.client.get(f"/projects/{project['id']}/diagrams/{diagram['id']}")
        self.assertEqual(editor.status_code, 200)
        editor_html = editor.get_data(as_text=True)
        self.assertIn("页面拓扑图", editor_html)
        self.assertIn("window.TT_EDITOR", editor_html)
        self.assertIn(f"diagram_id={diagram['id']}", editor_html)
        self.assertIn("导出 JSON", editor_html)

    def test_library_only_diagram_editor(self):
        project = self.new_project(name="页面项目")
        unbound = self.client.post(
            "/api/diagrams", json={"name": "未绑定库图", "content": canvas(shape("n1", "节点"))}
        ).get_json()

        response = self.client.get(f"/diagrams/{unbound['id']}")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("未绑定库图", html)
        self.assertIn("未绑定项目", html)
        self.assertIn("导出 JSON", html)
        self.assertIn("返回拓扑图库", html)
        self.assertIn("project: null", html)
        self.assertIn("diagram_id=", html)

        missing = self.client.get("/diagrams/d_missing")
        self.assertEqual(missing.status_code, 302)
        self.assertEqual(missing.headers["Location"], "/diagrams")

        bound = self.new_diagram(project["id"], name="项目图")
        redirect = self.client.get(f"/diagrams/{bound['id']}")
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(
            redirect.headers["Location"],
            f"/projects/{project['id']}/diagrams/{bound['id']}",
        )

    def test_missing_pages_redirect_to_dashboard(self):
        response = self.client.get("/projects/p_missing")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        project = self.new_project()
        response = self.client.get(f"/projects/{project['id']}/diagrams/d_missing")
        self.assertEqual(response.status_code, 302)

    def test_static_assets_are_served(self):
        for path in (
            "/static/css/topotash.css",
            "/static/css/ai.css",
            "/static/js/api.js",
            "/static/js/ai.js",
            "/static/js/tasks.js",
            "/static/js/diagram-actions.js",
            "/static/js/editor.js",
            "/static/apps/topology/index.html",
            "/static/apps/topology/topotash-topology-bridge.js",
            "/static/favicon.svg",
        ):
            response = self.client.get(path)
            try:
                self.assertEqual(response.status_code, 200, path)
                self.assertGreater(len(response.data), 0, path)
            finally:
                response.close()


class ErrorHandlingTest(ApiTestCase):
    def test_api_404_is_json(self):
        response = self.client.get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
        body = response.get_json()
        self.assertEqual(body["error"]["code"], "not_found")
        self.assertIn("message", body["error"])

    def test_api_method_not_allowed_is_json(self):
        response = self.client.put("/api/projects")
        self.assertEqual(response.status_code, 405)
        self.assertIn("error", response.get_json())

    def test_non_api_404_is_html(self):
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["Content-Type"])

    def test_validation_errors_use_consistent_envelope(self):
        response = self.client.post("/api/tasks", json={})
        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(body["error"]["code"], "project_required")
        self.assertTrue(body["error"]["message"])
