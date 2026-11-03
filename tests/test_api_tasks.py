"""Task REST API tests: CRUD, filters, subtasks, tags and diagram links."""
from __future__ import annotations

from db import get_db
from tests.support import ApiTestCase, canvas, shape


class TaskApiTest(ApiTestCase):
    # ------------------------------------------------------------- creation
    def test_create_requires_project_id(self):
        response = self.client.post("/api/tasks", json={"title": "没有项目"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "project_required")

    def test_create_unknown_project_is_404(self):
        response = self.client.post("/api/tasks", json={"project_id": "p_missing", "title": "x"})
        self.assertEqual(response.status_code, 404)

    def test_create_applies_defaults(self):
        project = self.new_project(stage="poc")
        task = self.new_task(project["id"], title="  确认环境  ", priority=9)
        self.assertEqual(task["title"], "确认环境")
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["status_label"], "待办")
        self.assertEqual(task["stage"], "poc")  # inherited from the project
        self.assertEqual(task["stage_label"], "POC 验证")
        self.assertEqual(task["priority"], 3)  # clamped to 0..3
        self.assertEqual(task["source"], "manual")
        self.assertEqual(task["tags"], [])
        self.assertEqual(task["subtasks"], [])
        self.assertEqual(task["project_name"], "测试项目")
        category = get_db().execute(
            "SELECT category_id FROM tasks WHERE id=?", (task["id"],)
        ).fetchone()["category_id"]
        self.assertTrue(category, "task should fall back to the project's default category")

    def test_create_increments_sort_order(self):
        project = self.new_project()
        first = self.new_task(project["id"], title="一")
        second = self.new_task(project["id"], title="二")
        rows = get_db().execute(
            "SELECT title, sort_order FROM tasks ORDER BY sort_order"
        ).fetchall()
        self.assertEqual([r["title"] for r in rows], ["一", "二"])
        self.assertLess(first["sort_order"], second["sort_order"])

    def test_create_with_tags_and_subtasks(self):
        project = self.new_project()
        task = self.new_task(
            project["id"],
            title="带子任务",
            tags=["重点", "重点", " "],
            subtasks=[{"title": "第一步"}, {"title": "第二步", "completed": True}],
        )
        self.assertEqual(task["tags"], ["重点"])
        self.assertEqual([s["title"] for s in task["subtasks"]], ["第一步", "第二步"])
        self.assertTrue(task["subtasks"][1]["completed"])
        self.assertEqual(task["subtask_total"], 2)
        self.assertEqual(task["subtask_done"], 1)

    # -------------------------------------------------------------- listing
    def test_list_filters(self):
        project = self.new_project()
        other = self.new_project(name="另一个项目")
        todo = self.new_task(project["id"], title="待办任务", priority=0, tags=["重点"])
        doing = self.new_task(project["id"], title="进行中任务", status="doing", priority=1)
        done = self.new_task(project["id"], title="已完成任务", status="done", priority=2)
        self.new_task(other["id"], title="别的项目")

        everything = self.get_json(f"/api/tasks?project_id={project['id']}")
        self.assertEqual(everything["total"], 3)
        self.assertEqual(everything["items"][-1]["id"], done["id"])  # done tasks sort last

        by_status = self.get_json(f"/api/tasks?project_id={project['id']}&status=doing")
        self.assertEqual([t["id"] for t in by_status["items"]], [doing["id"]])

        by_priority = self.get_json(f"/api/tasks?project_id={project['id']}&priority=0")
        self.assertEqual([t["id"] for t in by_priority["items"]], [todo["id"]])

        by_query = self.get_json("/api/tasks?q=进行中")
        self.assertEqual([t["id"] for t in by_query["items"]], [doing["id"]])

        by_tag = self.get_json("/api/tasks?tag=重点")
        self.assertEqual([t["id"] for t in by_tag["items"]], [todo["id"]])

        paged = self.get_json(f"/api/tasks?project_id={project['id']}&limit=1&offset=1")
        self.assertEqual(paged["total"], 3)
        self.assertEqual(len(paged["items"]), 1)
        self.assertEqual(paged["limit"], 1)
        self.assertEqual(paged["offset"], 1)

    def test_list_due_filters(self):
        project = self.new_project()
        overdue = self.new_task(project["id"], title="逾期", due_date="2020-01-01T09:00:00")
        future = self.new_task(project["id"], title="未来", due_date="2999-01-01T09:00:00")
        self.new_task(project["id"], title="无截止")
        done_overdue = self.new_task(
            project["id"], title="已完成逾期", due_date="2020-01-01T09:00:00", status="done"
        )

        self.assertEqual(
            {t["id"] for t in self.get_json(f"/api/tasks?project_id={project['id']}&due=overdue")["items"]},
            {overdue["id"]},
        )
        today = self.get_json(f"/api/tasks?project_id={project['id']}&due=today")
        self.assertEqual({t["id"] for t in today["items"]}, {overdue["id"], done_overdue["id"]})
        week = self.get_json(f"/api/tasks?project_id={project['id']}&due=week")
        self.assertEqual({t["id"] for t in week["items"]}, {overdue["id"], done_overdue["id"]})
        none = self.get_json(f"/api/tasks?project_id={project['id']}&due=none")
        self.assertEqual([t["title"] for t in none["items"]], ["无截止"])
        self.assertEqual(future["status"], "todo")

    def test_list_by_diagram(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="关联图纸")
        self.new_task(project["id"], title="没有关联")
        diagram = self.new_diagram(project["id"])
        self.api(
            "POST",
            f"/api/tasks/{task['id']}/diagrams",
            {"diagram_id": diagram["id"], "relation": "output"},
            status=201,
        )
        filtered = self.get_json(f"/api/tasks?diagram_id={diagram['id']}")
        self.assertEqual([t["id"] for t in filtered["items"]], [task["id"]])

    def test_list_order_updated(self):
        project = self.new_project()
        self.new_task(project["id"], title="A")
        self.new_task(project["id"], title="B")
        data = self.get_json(f"/api/tasks?project_id={project['id']}&order=updated")
        self.assertEqual(data["total"], 2)

    # --------------------------------------------------------------- detail
    def test_detail_includes_links(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="详情任务")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "服务器")))
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

        detail = self.get_json(f"/api/tasks/{task['id']}")
        self.assertEqual(detail["title"], "详情任务")
        self.assertEqual([d["id"] for d in detail["diagrams"]], [diagram["id"]])
        self.assertEqual(len(detail["node_links"]), 1)
        self.assertEqual(detail["node_links"][0]["node_key"], "n1")
        self.assertEqual(detail["node_links"][0]["node_label"], "服务器")
        self.assertEqual(detail["node_links"][0]["diagram_name"], "测试拓扑图")
        self.assertTrue(detail["node_links"][0]["is_primary"])

    def test_detail_unknown_is_404(self):
        response = self.client.get("/api/tasks/t_missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "task_not_found")

    # ---------------------------------------------------------------- patch
    def test_patch_updates_and_preserves_fields(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="原标题", description="原描述", priority=2)

        patched = self.api(
            "PATCH",
            f"/api/tasks/{task['id']}",
            {"title": "新标题", "status": "doing", "priority": 1},
        )
        self.assertEqual(patched["title"], "新标题")
        self.assertEqual(patched["description"], "原描述")
        self.assertEqual(patched["status"], "doing")
        self.assertEqual(patched["priority"], 1)
        self.assertIsNone(patched["completed_at"])

        # Invalid enums fall back to the current value instead of erroring.
        fallback = self.api("PATCH", f"/api/tasks/{task['id']}", {"stage": "nope", "status": "nope"})
        self.assertEqual(fallback["stage"], project["stage"])
        self.assertEqual(fallback["status"], "doing")

        clamped = self.api("PATCH", f"/api/tasks/{task['id']}", {"priority": -5})
        self.assertEqual(clamped["priority"], 0)

        cleared = self.api(
            "PATCH", f"/api/tasks/{task['id']}", {"due_date": None, "description": ""}
        )
        self.assertIsNone(cleared["due_date"])
        self.assertEqual(cleared["description"], "")

    def test_patch_done_sets_completed_at_and_syncs_node_badge(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="联动任务")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "负载均衡")))
        self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"task_id": task["id"]},
        )
        node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
        self.assertEqual(node["followup_status"], "todo")

        done = self.api("PATCH", f"/api/tasks/{task['id']}", {"status": "done"})
        self.assertIsNotNone(done["completed_at"])
        node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
        self.assertEqual(node["followup_status"], "done")
        self.assertEqual(node["primary_task"]["status"], "done")

        reopened = self.api("PATCH", f"/api/tasks/{task['id']}", {"status": "todo"})
        self.assertIsNone(reopened["completed_at"])
        node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
        self.assertEqual(node["followup_status"], "todo")

    def test_patch_unknown_is_404(self):
        response = self.client.patch("/api/tasks/t_missing", json={"title": "x"})
        self.assertEqual(response.status_code, 404)

    # --------------------------------------------------------------- delete
    def test_delete_clears_node_links_and_badge(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="要删除")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"task_id": task["id"]},
        )

        result = self.api("DELETE", f"/api/tasks/{task['id']}")
        self.assertTrue(result["deleted"])
        self.assertEqual(result["title"], "要删除")

        node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
        self.assertEqual(node["followup_status"], "none")
        self.assertEqual(node["linked_tasks"], [])
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM node_task_links").fetchone()["n"], 0
        )
        self.assertEqual(self.client.delete(f"/api/tasks/{task['id']}").status_code, 404)

    # ------------------------------------------------------------- subtasks
    def test_subtask_crud(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="父任务")

        created = self.api(
            "POST", f"/api/tasks/{task['id']}/subtasks", {"title": "子任务 A"}, status=201
        )
        self.assertEqual(created["title"], "子任务 A")
        self.assertFalse(created["completed"])

        patched = self.api(
            "PATCH",
            f"/api/tasks/{task['id']}/subtasks/{created['id']}",
            {"completed": True, "title": "子任务 A+"},
        )
        self.assertTrue(patched["completed"])
        self.assertEqual(patched["title"], "子任务 A+")

        detail = self.get_json(f"/api/tasks/{task['id']}")
        self.assertEqual(detail["subtask_done"], 1)
        self.assertEqual(detail["subtasks"][0]["title"], "子任务 A+")

        deleted = self.api("DELETE", f"/api/tasks/{task['id']}/subtasks/{created['id']}")
        self.assertTrue(deleted["deleted"])
        self.assertEqual(self.get_json(f"/api/tasks/{task['id']}")["subtasks"], [])

    def test_subtask_validation_and_errors(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="父任务")
        blank = self.client.post(f"/api/tasks/{task['id']}/subtasks", json={"title": "  "})
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.get_json()["error"]["code"], "title_required")

        missing_task = self.client.post("/api/tasks/t_missing/subtasks", json={"title": "x"})
        self.assertEqual(missing_task.status_code, 404)

        missing_sub = self.client.patch(
            f"/api/tasks/{task['id']}/subtasks/st_missing", json={"completed": True}
        )
        self.assertEqual(missing_sub.status_code, 404)
        self.assertEqual(missing_sub.get_json()["error"]["code"], "subtask_not_found")

        delete_missing = self.client.delete(
            f"/api/tasks/{task['id']}/subtasks/st_missing"
        )
        self.assertEqual(delete_missing.status_code, 404)

    # -------------------------------------------------------- diagram links
    def test_link_and_unlink_diagram(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="任务")
        diagram = self.new_diagram(project["id"], name="POC 部署图")

        linked = self.api(
            "POST",
            f"/api/tasks/{task['id']}/diagrams",
            {"diagram_id": diagram["id"], "relation": "output"},
            status=201,
        )
        self.assertEqual(linked["diagram_name"], "POC 部署图")

        # Linking twice is an upsert, not a 500.
        again = self.api(
            "POST",
            f"/api/tasks/{task['id']}/diagrams",
            {"diagram_id": diagram["id"], "relation": "reference"},
            status=201,
        )
        self.assertEqual(again["diagram_id"], diagram["id"])
        row = get_db().execute(
            "SELECT relation FROM task_diagrams WHERE task_id=?", (task["id"],)
        ).fetchone()
        self.assertEqual(row["relation"], "reference")

        unlinked = self.api("DELETE", f"/api/tasks/{task['id']}/diagrams/{diagram['id']}")
        self.assertTrue(unlinked["deleted"])
        self.assertEqual(
            self.client.delete(
                f"/api/tasks/{task['id']}/diagrams/{diagram['id']}"
            ).status_code,
            404,
        )

    def test_link_diagram_errors(self):
        project = self.new_project()
        other = self.new_project(name="另一个项目")
        task = self.new_task(project["id"], title="任务")
        foreign = self.new_diagram(other["id"], name="别家图纸")

        cross = self.client.post(
            f"/api/tasks/{task['id']}/diagrams", json={"diagram_id": foreign["id"]}
        )
        self.assertEqual(cross.status_code, 404)
        self.assertEqual(cross.get_json()["error"]["code"], "diagram_not_found")

        missing_task = self.client.post(
            "/api/tasks/t_missing/diagrams", json={"diagram_id": foreign["id"]}
        )
        self.assertEqual(missing_task.status_code, 404)

    # ----------------------------------------------------------------- tags
    def test_set_tags_replaces_and_dedupes(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="打标签", tags=["旧标签"])

        updated = self.api(
            "PUT", f"/api/tasks/{task['id']}/tags", {"tags": ["B", "A", "B", " "]}
        )
        self.assertEqual(updated["tags"], ["A", "B"])
        attached = {
            r["name"]
            for r in get_db().execute(
                """SELECT tg.name FROM task_tags tt JOIN tags tg ON tg.id=tt.tag_id
                   WHERE tt.task_id=?""",
                (task["id"],),
            )
        }
        self.assertEqual(attached, {"A", "B"})

        cleared = self.api("PUT", f"/api/tasks/{task['id']}/tags", {"tags": []})
        self.assertEqual(cleared["tags"], [])

        missing = self.client.put("/api/tasks/t_missing/tags", json={"tags": ["x"]})
        self.assertEqual(missing.status_code, 404)
