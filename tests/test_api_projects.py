"""Project REST API tests."""
from __future__ import annotations

from db import get_db
from tests.support import ApiTestCase, canvas, shape


class ProjectApiTest(ApiTestCase):
    # ------------------------------------------------------------- listing
    def test_empty_listing_has_constants(self):
        data = self.get_json("/api/projects")
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)
        self.assertEqual([s["key"] for s in data["stages"]], ["research", "proposal", "poc", "bidding"])
        self.assertEqual([s["key"] for s in data["statuses"]], ["active", "won", "lost", "paused"])

    def test_create_requires_name(self):
        response = self.client.post("/api/projects", json={"customer": "某客户"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "name_required")

    def test_create_applies_defaults(self):
        project = self.new_project(name="  项目 A  ")
        self.assertEqual(project["name"], "项目 A")  # trimmed
        self.assertEqual(project["stage"], "research")
        self.assertEqual(project["status"], "active")
        self.assertEqual(project["color"], "#5b6cf0")
        self.assertEqual(project["stage_label"], "需求调研")
        self.assertEqual(project["status_label"], "跟进中")
        self.assertEqual(project["task_total"], 0)
        self.assertEqual(project["task_progress"], 0)
        self.assertNotIn("todo_config", project)

        state = self.get_json(f"/api/projects/{project['id']}/todo-state")
        self.assertEqual(len(state["projects"]), 1)
        self.assertEqual(state["projects"][0]["name"], "默认分类")

    def test_create_normalises_invalid_stage_and_status(self):
        project = self.new_project(stage="nope", status="nope")
        self.assertEqual(project["stage"], "research")
        self.assertEqual(project["status"], "active")

    def test_list_filters_by_stage_status_and_query(self):
        a = self.new_project(name="银行私有云", customer="招商银行", owner="李娜", stage="poc")
        b = self.new_project(name="制造园区网", customer="三一重工", owner="王强", stage="bidding")
        self.new_project(name="政务云", customer="某市政府", owner="李娜", stage="research", status="won")

        by_stage = self.get_json("/api/projects?stage=poc")
        self.assertEqual([p["id"] for p in by_stage["items"]], [a["id"]])

        by_status = self.get_json("/api/projects?status=won")
        self.assertEqual([p["name"] for p in by_status["items"]], ["政务云"])

        by_query = self.get_json("/api/projects?q=招商")
        self.assertEqual([p["id"] for p in by_query["items"]], [a["id"]])

        by_owner = self.get_json("/api/projects?q=王强")
        self.assertEqual([p["id"] for p in by_owner["items"]], [b["id"]])

        everything = self.get_json("/api/projects?stage=all&status=all")
        self.assertEqual(everything["total"], 3)

    def test_list_is_sorted_by_updated_at_desc(self):
        first = self.new_project(name="先创建")
        second = self.new_project(name="后创建")
        # updated_at has second granularity, so give the first project a later stamp.
        get_db().execute(
            "UPDATE projects SET updated_at='2999-01-01T00:00:00Z' WHERE id=?", (first["id"],)
        )
        get_db().commit()
        items = self.get_json("/api/projects")["items"]
        self.assertEqual([p["id"] for p in items], [first["id"], second["id"]])

    # -------------------------------------------------------------- detail
    def test_detail_includes_related_collections(self):
        project = self.new_project(name="详情项目", stage="poc")
        task = self.new_task(project["id"], title="环境部署", status="doing")
        self.new_task(project["id"], title="已完成任务", status="done")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "核心交换机")))

        detail = self.get_json(f"/api/projects/{project['id']}")
        self.assertEqual(detail["task_total"], 2)
        self.assertEqual(detail["task_done"], 1)
        self.assertEqual(detail["task_doing"], 1)
        self.assertEqual(detail["task_progress"], 50)
        self.assertEqual(detail["diagram_count"], 1)
        self.assertEqual(len(detail["diagrams"]), 1)
        self.assertEqual(detail["diagrams"][0]["id"], diagram["id"])
        self.assertEqual([t["id"] for t in detail["recent_tasks"]], [task["id"]])
        self.assertTrue(any(a["action"] == "create" for a in detail["activity"]))
        self.assertEqual(detail["followup_nodes"], [])

    def test_detail_reports_followup_nodes(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "防火墙")))
        self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"status": "todo"},
            status=200,
        )

        listing = self.get_json("/api/projects")["items"][0]
        self.assertEqual(listing["followup_count"], 1)
        self.assertEqual(len(listing["followup_nodes"]), 1)

        detail = self.get_json(f"/api/projects/{project['id']}")
        self.assertEqual(detail["followup_count"], 1)
        self.assertEqual(detail["followup_nodes"][0]["label"], "防火墙")
        self.assertEqual(detail["followup_nodes"][0]["diagram_name"], "测试拓扑图")

    def test_detail_unknown_project_is_404(self):
        response = self.client.get("/api/projects/p_missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "project_not_found")

    # --------------------------------------------------------------- patch
    def test_patch_updates_fields(self):
        project = self.new_project(name="旧名")
        patched = self.api(
            "PATCH",
            f"/api/projects/{project['id']}",
            {"name": "新名", "stage": "poc", "owner": "张伟", "status": "won"},
        )
        self.assertEqual(patched["name"], "新名")
        self.assertEqual(patched["stage"], "poc")
        self.assertEqual(patched["stage_label"], "POC 验证")
        self.assertEqual(patched["owner"], "张伟")
        self.assertEqual(patched["status"], "won")

        log = get_db().execute(
            "SELECT * FROM activity_log WHERE action='update' AND project_id=?",
            (project["id"],),
        ).fetchall()
        self.assertTrue(log)

    def test_patch_rejects_empty_payload_and_unknown_project(self):
        project = self.new_project()
        empty = self.client.patch(f"/api/projects/{project['id']}", json={})
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.get_json()["error"]["code"], "empty_patch")

        missing = self.client.patch("/api/projects/p_missing", json={"name": "x"})
        self.assertEqual(missing.status_code, 404)

    # -------------------------------------------------------------- delete
    def test_delete_cascades_children(self):
        project = self.new_project(name="待删除")
        task = self.new_task(project["id"], title="任务", tags=["重点"], subtasks=[{"title": "子任务"}])
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        self.api(
            "POST",
            f"/api/tasks/{task['id']}/diagrams",
            {"diagram_id": diagram["id"]},
            status=201,
        )
        self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"task_id": task["id"]},
        )

        result = self.api("DELETE", f"/api/projects/{project['id']}")
        self.assertTrue(result["deleted"])
        self.assertEqual(result["name"], "待删除")

        db = get_db()
        for table in (
            "projects",
            "tasks",
            "subtasks",
            "tags",
            "task_tags",
            "task_categories",
            "diagrams",
            "diagram_nodes",
            "node_task_links",
            "task_diagrams",
            "activity_log",
        ):
            count = db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            self.assertEqual(count, 0, f"{table} should be empty after cascade")

        missing = self.client.delete(f"/api/projects/{project['id']}")
        self.assertEqual(missing.status_code, 404)

    # ----------------------------------------------------------- todo-state
    def test_todo_state_roundtrip(self):
        project = self.new_project(name="任务台项目", stage="proposal")
        state = self.get_json(f"/api/projects/{project['id']}/todo-state")
        category_id = state["projects"][0]["id"]

        payload = {
            "projects": [{"id": category_id, "name": "售前", "color": "#123456"}],
            "tags": ["重点", "待确认"],
            "tasks": [
                {
                    "id": "t_manual_1",
                    "title": "写方案",
                    "status": "doing",
                    "priority": 1,
                    "stage": "proposal",
                    "projectId": category_id,
                    "dueDate": "2026-01-01T09:00:00",
                    "tags": ["重点"],
                    "subtasks": [{"id": "st_1", "title": "大纲", "completed": True}],
                    "order": 3,
                }
            ],
            "aiConfig": {"apiBase": "https://example.invalid/v1", "apiKey": "sk-legacy", "model": "m"},
        }
        updated = self.api("PUT", f"/api/projects/{project['id']}/todo-state", payload)
        self.assertEqual(len(updated["tasks"]), 1)
        self.assertEqual(updated["tasks"][0]["title"], "写方案")
        self.assertEqual(updated["tasks"][0]["dueDate"], "2026-01-01T09:00:00")
        self.assertEqual(updated["tasks"][0]["subtasks"][0]["title"], "大纲")
        self.assertEqual(updated["projects"][0]["name"], "售前")
        self.assertEqual(sorted(updated["tags"]), ["待确认", "重点"])
        self.assertEqual(updated["aiConfig"]["apiBase"], "https://example.invalid/v1")
        self.assertEqual(updated["topotash"]["projectId"], project["id"])

        # Legacy AI config must never leak through the normal project payload.
        detail = self.get_json(f"/api/projects/{project['id']}")
        self.assertNotIn("todo_config", detail)

        # Removing a task explicitly deletes it.
        payload["tasks"] = []
        payload["deleted_task_ids"] = ["t_manual_1"]
        emptied = self.api("PUT", f"/api/projects/{project['id']}/todo-state", payload)
        self.assertEqual(emptied["tasks"], [])
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"], 0
        )

    def test_todo_state_cannot_hijack_another_projects_task(self):
        project_a = self.new_project(name="A")
        project_b = self.new_project(name="B")
        task_a = self.new_task(project_a["id"], title="A 的任务")

        payload = {
            "projects": [],
            "tasks": [{"id": task_a["id"], "title": "被篡改", "projectId": None}],
        }
        self.api("PUT", f"/api/projects/{project_b['id']}/todo-state", payload)

        self.assertEqual(
            get_db().execute("SELECT title FROM tasks WHERE id=?", (task_a["id"],)).fetchone()["title"],
            "A 的任务",
        )
        b_tasks = self.get_json(f"/api/tasks?project_id={project_b['id']}")["items"]
        self.assertEqual(len(b_tasks), 1)
        self.assertNotEqual(b_tasks[0]["id"], task_a["id"])
        self.assertEqual(b_tasks[0]["title"], "被篡改")

    def test_todo_state_unknown_project_is_404(self):
        response = self.client.get("/api/projects/p_missing/todo-state")
        self.assertEqual(response.status_code, 404)
