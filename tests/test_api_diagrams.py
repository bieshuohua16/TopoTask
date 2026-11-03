"""Diagram, canvas and node-follow-up API tests."""
from __future__ import annotations

from db import get_db
from tests.support import ApiTestCase, canvas, shape


class DiagramApiTest(ApiTestCase):
    # ------------------------------------------------------------ documents
    def test_create_requires_project(self):
        response = self.client.post("/api/diagrams", json={"name": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "project_required")

        missing = self.client.post("/api/diagrams", json={"project_id": "p_missing"})
        self.assertEqual(missing.status_code, 404)

    def test_create_without_content_uses_empty_canvas(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"])
        self.assertEqual(diagram["node_count"], 0)
        self.assertEqual(diagram["kind"], "topology")
        self.assertEqual(diagram["version"], 1)
        self.assertEqual(diagram["followup_count"], 0)

        content = self.get_json(f"/api/diagrams/{diagram['id']}/content")
        self.assertEqual(content["shapes"], {})
        self.assertEqual(content["_topotash"]["diagramId"], diagram["id"])

    def test_create_with_shapes_indexes_nodes(self):
        project = self.new_project()
        doc = canvas(shape("n1", "交换机"), shape("n2", "防火墙"), shape("e1", "连线", type="connector"))
        diagram = self.new_diagram(project["id"], doc)
        self.assertEqual(diagram["node_count"], 2)

        nodes = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"]
        self.assertEqual({n["node_key"] for n in nodes}, {"n1", "n2"})
        self.assertEqual({n["label"] for n in nodes}, {"交换机", "防火墙"})
        self.assertTrue(all(n["followup_status"] == "none" for n in nodes))

    def test_list_filters_by_project_and_query(self):
        project = self.new_project()
        other = self.new_project(name="另一个项目")
        mine = self.new_diagram(project["id"], name="POC 部署图")
        self.new_diagram(other["id"], name="架构总览")

        by_project = self.get_json(f"/api/diagrams?project_id={project['id']}")
        self.assertEqual([d["id"] for d in by_project["items"]], [mine["id"]])
        self.assertEqual(by_project["items"][0]["project_name"], "测试项目")

        by_query = self.get_json("/api/diagrams?q=POC")
        self.assertEqual([d["id"] for d in by_query["items"]], [mine["id"]])
        self.assertEqual(self.get_json("/api/diagrams")["total"], 2)

    def test_detail_includes_nodes_and_task_links(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="部署验证")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "应用服务器")))
        self.api("POST", f"/api/tasks/{task['id']}/diagrams", {"diagram_id": diagram["id"]}, status=201)
        self.api("POST", f"/api/diagrams/{diagram['id']}/nodes/n1/followup", {"task_id": task["id"]})

        detail = self.get_json(f"/api/diagrams/{diagram['id']}")
        self.assertEqual(detail["project_name"], "测试项目")
        self.assertEqual(len(detail["nodes"]), 1)
        self.assertEqual(detail["nodes"][0]["followup_status"], "todo")
        self.assertEqual(detail["nodes"][0]["primary_task"]["task_id"], task["id"])
        self.assertEqual(len(detail["task_links"]), 1)
        self.assertEqual(detail["task_links"][0]["title"], "部署验证")

    def test_patch_and_delete(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))

        patched = self.api(
            "PATCH",
            f"/api/diagrams/{diagram['id']}",
            {"name": "新名称", "kind": "deployment", "description": "说明"},
        )
        self.assertEqual(patched["name"], "新名称")
        self.assertEqual(patched["kind"], "deployment")
        self.assertEqual(patched["description"], "说明")
        self.assertEqual(patched["node_count"], 1)

        empty = self.client.patch(f"/api/diagrams/{diagram['id']}", json={})
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.get_json()["error"]["code"], "empty_patch")

        blank = self.client.patch(f"/api/diagrams/{diagram['id']}", json={"name": "  "})
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.get_json()["error"]["code"], "name_required")

        self.assertEqual(self.client.patch("/api/diagrams/d_missing", json={"name": "x"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/diagrams/d_missing").status_code, 404)

        deleted = self.api("DELETE", f"/api/diagrams/{diagram['id']}")
        self.assertTrue(deleted["deleted"])
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM diagram_nodes").fetchone()["n"], 0
        )

    # ------------------------------------------------------------- content
    def test_save_content_updates_version_and_prunes_nodes(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="跟进任务")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "旧节点"), shape("n2", "保留")))
        self.api("POST", f"/api/diagrams/{diagram['id']}/nodes/n1/followup", {"task_id": task["id"]})

        new_doc = canvas(shape("n2", "保留"), shape("n3", "新增"))
        saved = self.api("PUT", f"/api/diagrams/{diagram['id']}/content", {"content": new_doc})
        self.assertTrue(saved["saved"])
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["node_count"], 2)

        nodes = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"]
        self.assertEqual({n["node_key"] for n in nodes}, {"n2", "n3"})
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) AS n FROM node_task_links WHERE diagram_id=?", (diagram["id"],)
            ).fetchone()["n"],
            0,
        )

        again = self.api("PUT", f"/api/diagrams/{diagram['id']}/content", {"content": new_doc})
        self.assertEqual(again["version"], 3)

    def test_save_content_strips_runtime_metadata(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"])
        doc = canvas(shape("n1", "节点", tt={"status": "done"}), _topotash={"diagramId": "x"})
        self.api("PUT", f"/api/diagrams/{diagram['id']}/content", {"content": doc})

        raw = get_db().execute(
            "SELECT content_json FROM diagrams WHERE id=?", (diagram["id"],)
        ).fetchone()["content_json"]
        self.assertNotIn('"tt"', raw)
        self.assertNotIn("_topotash", raw)

        # The GET response re-injects the runtime follow-up metadata on purpose.
        stored = self.get_json(f"/api/diagrams/{diagram['id']}/content")
        self.assertEqual(stored["_topotash"]["diagramId"], diagram["id"])

    def test_save_content_validation(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"])
        response = self.client.put(
            f"/api/diagrams/{diagram['id']}/content", json={"shapes": "nope"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "invalid_content")

        missing = self.client.put("/api/diagrams/d_missing/content", json={"shapes": {}})
        self.assertEqual(missing.status_code, 404)

    # --------------------------------------------------------------- nodes
    def test_patch_node(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        self.api("PATCH", f"/api/diagrams/{diagram['id']}/nodes/n1", {"note": "等待客户确认"})
        self.api("PATCH", f"/api/diagrams/{diagram['id']}/nodes/n1", {"label": "新标签"})

        node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
        self.assertEqual(node["note"], "等待客户确认")
        self.assertEqual(node["label"], "新标签")

        empty = self.client.patch(f"/api/diagrams/{diagram['id']}/nodes/n1", json={})
        self.assertEqual(empty.status_code, 400)
        bad = self.client.patch(
            f"/api/diagrams/{diagram['id']}/nodes/n1", json={"followup_status": "nope"}
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.get_json()["error"]["code"], "invalid_status")
        self.assertEqual(
            self.client.patch(f"/api/diagrams/{diagram['id']}/nodes/n_missing", json={"note": "x"}).status_code,
            404,
        )

    def test_followup_status_only(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        result = self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"status": "doing", "note": "跟进中"},
        )
        self.assertEqual(result["node"]["followup_status"], "doing")
        self.assertEqual(result["node"]["note"], "跟进中")
        self.assertNotIn("task", result)

        overview = self.get_json("/api/views/overview")
        self.assertEqual(overview["followup_total"], 1)

        bad = self.client.post(
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup", json={"status": "nope"}
        )
        self.assertEqual(bad.status_code, 400)

        missing_node = self.client.post(
            f"/api/diagrams/{diagram['id']}/nodes/n_missing/followup", json={"status": "todo"}
        )
        self.assertEqual(missing_node.status_code, 404)
        self.assertIn("请先保存", missing_node.get_json()["error"]["message"])

    def test_followup_can_create_task(self):
        project = self.new_project(stage="poc")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "核心交换机")))
        result = self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"create_task": {"title": "确认堆叠方案", "priority": 1}},
        )
        task = result["task"]
        self.assertEqual(task["title"], "确认堆叠方案")
        self.assertEqual(task["source"], "diagram")
        self.assertEqual(task["stage"], "poc")
        self.assertEqual(task["priority"], 1)
        full = self.get_json(f"/api/tasks/{task['id']}")
        self.assertEqual(full["tags"], ["拓扑跟进"])
        self.assertIn("核心交换机", task["description"])
        self.assertEqual(result["node"]["followup_status"], "todo")
        self.assertEqual(result["node"]["primary_task"]["task_id"], task["id"])

        auto = self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"create_task": {"description": "只给描述，标题走默认值"}},
        )
        self.assertEqual(auto["task"]["title"], "跟进：核心交换机")

    def test_followup_links_existing_task_with_project_guard(self):
        project = self.new_project()
        other = self.new_project(name="另一个项目")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        mine = self.new_task(project["id"], title="本项目任务", status="doing")
        foreign = self.new_task(other["id"], title="别家任务")

        linked = self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup",
            {"task_id": mine["id"]},
        )
        self.assertEqual(linked["node"]["followup_status"], "doing")
        self.assertEqual(linked["node"]["primary_task"]["task_id"], mine["id"])

        mismatch = self.client.post(
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup", json={"task_id": foreign["id"]}
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.get_json()["error"]["code"], "project_mismatch")

        missing = self.client.post(
            f"/api/diagrams/{diagram['id']}/nodes/n1/followup", json={"task_id": "t_missing"}
        )
        self.assertEqual(missing.status_code, 404)

    def test_node_links_primary_and_removal(self):
        project = self.new_project()
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        first = self.new_task(project["id"], title="任务一", status="todo")
        second = self.new_task(project["id"], title="任务二", status="doing")

        added = self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/links",
            {"task_id": first["id"]},
            status=201,
        )
        self.assertEqual(len(added["linked_tasks"]), 1)
        self.assertFalse(added["linked_tasks"][0]["is_primary"])
        self.assertEqual(added["followup_status"], "none")

        primary = self.api(
            "POST",
            f"/api/diagrams/{diagram['id']}/nodes/n1/links",
            {"task_id": second["id"], "is_primary": True},
            status=201,
        )
        self.assertEqual(len(primary["linked_tasks"]), 2)
        self.assertEqual(primary["primary_task"]["task_id"], second["id"])
        self.assertEqual(primary["followup_status"], "doing")

        removed = self.api(
            "DELETE", f"/api/diagrams/{diagram['id']}/nodes/n1/links/{second['id']}"
        )
        self.assertEqual(removed["primary_task"], None)
        self.assertEqual(removed["followup_status"], "todo")  # falls back to the remaining task

        self.api("DELETE", f"/api/diagrams/{diagram['id']}/nodes/n1/links/{first['id']}")
        node = self.get_json(f"/api/diagrams/{diagram['id']}/nodes")["items"][0]
        self.assertEqual(node["followup_status"], "none")

        self.assertEqual(
            self.client.delete(
                f"/api/diagrams/{diagram['id']}/nodes/n1/links/{first['id']}"
            ).status_code,
            404,
        )

    def test_node_links_validation(self):
        project = self.new_project()
        other = self.new_project(name="另一个项目")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        foreign = self.new_task(other["id"], title="别家任务")

        missing_node = self.client.post(
            f"/api/diagrams/{diagram['id']}/nodes/n_missing/links", json={"task_id": foreign["id"]}
        )
        self.assertEqual(missing_node.status_code, 404)

        mismatch = self.client.post(
            f"/api/diagrams/{diagram['id']}/nodes/n1/links", json={"task_id": foreign["id"]}
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.get_json()["error"]["code"], "project_mismatch")

        no_task = self.client.post(
            f"/api/diagrams/{diagram['id']}/nodes/n1/links", json={"task_id": "t_missing"}
        )
        self.assertEqual(no_task.status_code, 404)

    def test_content_roundtrip_keeps_followup_metadata(self):
        project = self.new_project()
        task = self.new_task(project["id"], title="跟进")
        diagram = self.new_diagram(project["id"], canvas(shape("n1", "节点")))
        self.api("POST", f"/api/diagrams/{diagram['id']}/nodes/n1/followup", {"task_id": task["id"]})

        content = self.get_json(f"/api/diagrams/{diagram['id']}/content")
        self.assertEqual(content["shapes"]["n1"]["tt"]["status"], "todo")
        self.assertEqual(content["shapes"]["n1"]["tt"]["tasks"][0]["title"], "跟进")
