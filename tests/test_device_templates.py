"""Global device template library and CSV import tests."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path

_TMP_DIR = Path(os.environ.get("TEMP") or tempfile.gettempdir())
os.environ["TOPOTASH_DB"] = str(_TMP_DIR / ("tt_templates_bootstrap_%s.db" % os.getpid()))

from app import create_app  # noqa: E402


def tearDownModule():
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(os.environ["TOPOTASH_DB"] + suffix).unlink()
        except FileNotFoundError:
            pass


CSV_TEXT = (
    "类别,品牌,型号,关键参数,单位,参考单价,备注\n"
    "网络,华为,S12700E-8,48×10GE,台,168000,已有模板\n"
    "网络,华为,S5735-L24T4X,24×GE,台,4800,新增\n"
    "安全,深信服,AF-2000,40Gbps,台,98000,新增\n"
    "服务器,浪潮,NF5280M6,2U,台,abc,单价写错\n"
)


class DeviceTemplateTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = str(
            _TMP_DIR / ("tt_templates_%s_%s.db" % (os.getpid(), self._testMethodName))
        )
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.ctx.pop()
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(self.db_path + suffix).unlink()
            except FileNotFoundError:
                pass

    def _create(self, name="核心交换机", **extra):
        payload = {
            "name": name,
            "category": "network",
            "brand": "华为",
            "model": "S12700E-8",
            "spec": "48×10GE",
            "unit": "台",
            "unit_price": 168000,
            "note": "",
        }
        payload.update(extra)
        return self.client.post("/api/device-templates", json=payload)

    def _csv_file(self):
        return io.BytesIO(("\ufeff" + CSV_TEXT).encode("utf-8"))

    def test_template_crud_filters_and_duplicate(self):
        self.assertEqual(self.client.get("/api/device-templates").get_json()["summary"]["total"], 0)
        first = self._create()
        self.assertEqual(first.status_code, 201)
        created = first.get_json()
        self.assertEqual(created["category_label"], "网络")
        self.assertEqual(created["unit_price"], 168000)

        second = self._create(
            name="边界防火墙", category="security", brand="深信服",
            model="AF-2000", spec="40Gbps", unit_price=98000,
        )
        self.assertEqual(second.status_code, 201)

        data = self.client.get("/api/device-templates?q=防火墙").get_json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["name"], "边界防火墙")
        self.assertEqual(data["summary"]["total"], 2)
        self.assertEqual(data["summary"]["brands"], 2)
        self.assertIn("华为", data["brands"])

        patched = self.client.patch(
            "/api/device-templates/" + created["id"],
            json={"spec": "48×10GE, 双主控", "unit_price": 170000},
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.get_json()["unit_price"], 170000)

        duplicate = self._create()
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()["error"]["code"], "template_duplicate")

        deleted = self.client.delete("/api/device-templates/" + created["id"])
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/device-templates").get_json()["summary"]["total"], 1)

    def test_sample_csv_has_bom_and_fixed_headers(self):
        response = self.client.get("/api/device-templates/sample.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        text = response.get_data(as_text=True)
        self.assertTrue(text.startswith("\ufeff"))
        self.assertEqual(
            text.lstrip("\ufeff").splitlines()[0],
            "类别,品牌,型号,关键参数,单位,参考单价,备注",
        )

    def test_preview_and_import_skip(self):
        self._create()
        preview = self.client.post(
            "/api/device-templates/import",
            data={"file": (self._csv_file(), "templates.csv"), "dry_run": "1"},
            content_type="multipart/form-data",
        )
        self.assertEqual(preview.status_code, 200)
        summary = preview.get_json()["summary"]
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["new"], 2)
        self.assertEqual(summary["duplicate"], 1)
        self.assertEqual(summary["invalid"], 1)

        result = self.client.post(
            "/api/device-templates/import",
            data={"file": (self._csv_file(), "templates.csv"), "mode": "skip"},
            content_type="multipart/form-data",
        )
        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertEqual(body["imported"], 2)
        self.assertEqual(body["skipped"], 1)
        self.assertEqual(body["invalid"], 1)
        self.assertEqual(self.client.get("/api/device-templates").get_json()["summary"]["total"], 3)

    def test_import_overwrite_updates_existing(self):
        self._create(spec="旧参数", unit_price=100)
        result = self.client.post(
            "/api/device-templates/import",
            data={"file": (self._csv_file(), "templates.csv"), "mode": "overwrite"},
            content_type="multipart/form-data",
        )
        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertEqual(body["updated"], 1)
        self.assertEqual(body["imported"], 2)
        items = self.client.get("/api/device-templates?q=核心交换机").get_json()["items"]
        self.assertEqual(items[0]["spec"], "48×10GE")
        self.assertEqual(items[0]["unit_price"], 168000)

    def test_template_without_name_defaults_server(self):
        response = self.client.post(
            "/api/device-templates",
            json={"brand": "华为", "model": "2288H V6", "spec": "2U, 2×Xeon", "unit_price": 56000},
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["name"], "2288H V6")
        self.assertEqual(data["category"], "server")
        self.assertEqual(data["display_label"], "华为 2288H V6")

        duplicate = self.client.post(
            "/api/device-templates",
            json={"brand": "华为", "model": "2288H V6"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()["error"]["code"], "template_duplicate")

    def test_page_route_and_assets(self):
        response = self.client.get("/device-templates")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for marker in ("模板库", "templateTableBody", "device-templates.js", "导入 CSV"):
            self.assertIn(marker, html)
        self.assertIn('data-page="templates"', html)


if __name__ == "__main__":
    unittest.main()
