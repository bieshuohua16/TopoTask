"""Device list and device-node link tests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

_TMP_DIR = Path(os.environ.get("TEMP") or tempfile.gettempdir())
os.environ["TOPOTASH_DB"] = str(_TMP_DIR / ("tt_devices_bootstrap_%s.db" % os.getpid()))

from app import create_app  # noqa: E402


def tearDownModule():
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(os.environ["TOPOTASH_DB"] + suffix).unlink()
        except FileNotFoundError:
            pass


class DeviceTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = str(
            _TMP_DIR / ("tt_devices_%s_%s.db" % (os.getpid(), self._testMethodName))
        )
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()
        self.project = self.client.post(
            "/api/projects", json={"name": "设备测试项目", "stage": "poc"}
        ).get_json()
        self.project_id = self.project["id"]
        self.diagram = self.client.post(
            "/api/diagrams",
            json={"project_id": self.project_id, "name": "POC 环境部署图", "kind": "deployment"},
        ).get_json()
        self.diagram_id = self.diagram["id"]
        self._save_content(["n1", "n2"])

    def tearDown(self):
        self.ctx.pop()
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(self.db_path + suffix).unlink()
            except FileNotFoundError:
                pass

    def _save_content(self, node_ids):
        shapes = {}
        for index, node_id in enumerate(node_ids):
            shapes[node_id] = {
                "type": "shape", "id": node_id,
                "text": "核心交换机" if node_id == "n1" else "边界防火墙",
                "kind": "switch" if node_id == "n1" else "firewall",
                "x": 20 + index * 160, "y": 20, "w": 120, "h": 80,
            }
        content = {
            "app": "topotash", "version": 2, "shapes": shapes,
            "order": list(node_ids), "groups": {}, "imagePool": {},
        }
        response = self.client.put(
            "/api/diagrams/%s/content" % self.diagram_id, json={"content": content}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["node_count"], len(node_ids))

    def _create_device(self, **overrides):
        payload = {
            "project_id": self.project_id,
            "name": "核心交换机",
            "category": "network",
            "brand": "华为",
            "model": "S12700E-8",
            "spec": "48×10GE",
            "quantity": 2,
            "unit": "台",
            "status": "selected",
            "unit_price": 168000,
            "vendor": "华为技术有限公司",
            "owner": "张伟",
            "note": "POC 主交换",
            "links": [
                {"diagram_id": self.diagram_id, "node_key": "n1", "quantity": 2},
            ],
        }
        payload.update(overrides)
        response = self.client.post("/api/devices", json=payload)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()

    def test_device_crud_list_summary_and_filters(self):
        device = self._create_device()
        self.assertEqual(device["category_label"], "网络")
        self.assertEqual(device["status_label"], "已选型")
        self.assertEqual(device["total"], 336000)
        self.assertEqual(len(device["linked_nodes"]), 1)
        self.assertEqual(device["linked_nodes"][0]["node_label"], "核心交换机")

        listing = self.client.get("/api/devices?project_id=%s" % self.project_id).get_json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["summary"]["types"], 1)
        self.assertEqual(listing["summary"]["quantity"], 2)
        self.assertEqual(listing["summary"]["linked_types"], 1)
        self.assertEqual(listing["summary"]["node_count"], 1)
        self.assertEqual(listing["summary"]["amount"], 336000)
        self.assertTrue(any(item["key"] == "server" for item in listing["categories"]))

        linked = self.client.get(
            "/api/devices?project_id=%s&linked=yes" % self.project_id
        ).get_json()
        self.assertEqual(linked["total"], 1)
        unlinked = self.client.get(
            "/api/devices?project_id=%s&linked=no" % self.project_id
        ).get_json()
        self.assertEqual(unlinked["total"], 0)

        search = self.client.get(
            "/api/devices?project_id=%s&q=S12700" % self.project_id
        ).get_json()
        self.assertEqual(search["total"], 1)
        none = self.client.get(
            "/api/devices?project_id=%s&q=not-found" % self.project_id
        ).get_json()
        self.assertEqual(none["total"], 0)

        patched = self.client.patch(
            "/api/devices/%s" % device["id"],
            json={"quantity": 3, "unit_price": 1000, "status": "quoted"},
        ).get_json()
        self.assertEqual(patched["total"], 3000)
        self.assertEqual(patched["status_label"], "已报价")

        deleted = self.client.delete("/api/devices/%s" % device["id"]).get_json()
        self.assertTrue(deleted["deleted"])
        self.assertEqual(
            self.client.get("/api/devices?project_id=%s" % self.project_id).get_json()["total"],
            0,
        )

    def test_node_link_unlink_and_canvas_payload(self):
        device = self._create_device(links=[])
        linked = self.client.post(
            "/api/diagrams/%s/nodes/n1/devices" % self.diagram_id,
            json={"device_id": device["id"], "quantity": 2},
        )
        self.assertEqual(linked.status_code, 201)
        node = linked.get_json()["node"]
        self.assertEqual(len(node["linked_devices"]), 1)
        self.assertEqual(node["linked_devices"][0]["quantity"], 2)

        content = self.client.get(
            "/api/diagrams/%s/content" % self.diagram_id
        ).get_json()
        self.assertEqual(len(content["shapes"]["n1"]["tt"]["devices"]), 1)
        self.assertEqual(content["shapes"]["n1"]["tt"]["devices"][0]["name"], "核心交换机")

        nodes = self.client.get(
            "/api/diagrams/%s/nodes" % self.diagram_id
        ).get_json()["items"]
        n1 = next(item for item in nodes if item["node_key"] == "n1")
        self.assertEqual(len(n1["linked_devices"]), 1)

        removed = self.client.delete(
            "/api/diagrams/%s/nodes/n1/devices/%s" % (self.diagram_id, device["id"])
        )
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.get_json()["node"]["linked_devices"], [])

    def test_create_device_from_node(self):
        response = self.client.post(
            "/api/diagrams/%s/nodes/n2/devices" % self.diagram_id,
            json={
                "create_device": {
                    "name": "边界防火墙",
                    "category": "security",
                    "brand": "深信服",
                    "model": "AF-2000",
                    "quantity": 1,
                }
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["device"]["name"], "边界防火墙")
        self.assertEqual(data["node"]["linked_devices"][0]["device_id"], data["device"]["id"])
        listing = self.client.get(
            "/api/devices?project_id=%s&category=security" % self.project_id
        ).get_json()
        self.assertEqual(listing["total"], 1)

    def test_node_removal_cleans_device_links(self):
        device = self._create_device()
        self._save_content(["n2"])
        from db import get_db

        links = get_db().execute(
            "SELECT COUNT(*) AS n FROM device_node_links WHERE device_id=?", (device["id"],)
        ).fetchone()["n"]
        self.assertEqual(links, 0)
        self.assertEqual(
            self.client.get("/api/devices/%s" % device["id"]).status_code, 200
        )

    def test_device_crud_links_are_replaced_atomically(self):
        device = self._create_device()
        patched = self.client.patch(
            "/api/devices/%s" % device["id"],
            json={
                "links": [
                    {"diagram_id": self.diagram_id, "node_key": "n2", "quantity": 1},
                ]
            },
        ).get_json()
        self.assertEqual(len(patched["linked_nodes"]), 1)
        self.assertEqual(patched["linked_nodes"][0]["node_key"], "n2")

    def test_csv_export(self):
        self._create_device()
        response = self.client.get(
            "/api/projects/%s/devices/export.csv" % self.project_id
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["Content-Type"])
        self.assertIn("attachment", response.headers["Content-Disposition"])
        body = response.get_data(as_text=True)
        self.assertTrue(body.startswith("\ufeff"))
        self.assertIn("设备名称,类别,品牌,型号", body)
        self.assertIn("核心交换机,网络,华为,S12700E-8", body)

    def test_project_delete_cascades_devices(self):
        device = self._create_device()
        self.assertEqual(
            self.client.delete("/api/projects/%s" % self.project_id).status_code, 200
        )
        from db import get_db

        self.assertEqual(
            get_db().execute("SELECT COUNT(*) AS n FROM devices WHERE id=?", (device["id"],)).fetchone()["n"],
            0,
        )
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) AS n FROM device_node_links WHERE device_id=?", (device["id"],)
            ).fetchone()["n"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
