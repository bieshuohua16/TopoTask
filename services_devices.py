"""项目设备清单（BOM）与设备-拓扑节点关联。

Design:
- devices belong to a project; device_node_links is many-to-many and stores
  the quantity deployed at that node.
- Device CRUD accepts an optional ``links`` array (full replacement) so the
  edit modal can save fields and node links in one transaction.
- Topology endpoints can also link/unlink a single device without touching the
  rest of the device fields.
"""
from __future__ import annotations

import csv
import io
import sqlite3
from urllib.parse import quote

from db import ApiError, get_db, new_id, utcnow
from services import ensure_project, limit_text, log_activity, text

CATEGORIES = ("server", "storage", "network", "security", "software", "other")
CATEGORY_LABELS = {
    "server": "服务器",
    "storage": "存储",
    "network": "网络",
    "security": "安全",
    "software": "软件",
    "other": "其他",
}
CATEGORY_ORDER = {key: index for index, key in enumerate(CATEGORIES)}

STATUSES = ("planned", "selected", "quoted", "ordered", "delivered")
STATUS_LABELS = {
    "planned": "规划中",
    "selected": "已选型",
    "quoted": "已报价",
    "ordered": "已下单",
    "delivered": "已到货",
}
UNITS = ("台", "套", "节点", "个", "块")

DEVICE_FIELDS = (
    "name", "category", "brand", "model", "spec", "quantity", "unit", "status",
    "unit_price", "currency", "vendor", "owner", "note", "sort_order",
)


def _clean_category(value, fallback: str = "other") -> str:
    value = text(value)
    return value if value in CATEGORIES else fallback


def _clean_status(value, fallback: str = "planned") -> str:
    value = text(value)
    return value if value in STATUSES else fallback


def _clean_unit(value, fallback: str = "台") -> str:
    value = text(value)[:16]
    return value or fallback


def _clean_quantity(value, fallback: int = 1) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, number)


def _clean_price(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, number), 2)


# Excel/WPS 会把以这些字符开头的单元格当作公式执行，导出时需要加前缀转义
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """Neutralise spreadsheet formulas in exported text cells."""
    raw = "" if value is None else str(value)
    return "'" + raw if raw.startswith(_CSV_FORMULA_PREFIXES) else raw


def clean_device_payload(data: dict, partial: bool = False) -> dict:
    if not isinstance(data, dict):
        raise ApiError("设备数据格式错误", 400, "invalid_device")
    out = {}
    for key in DEVICE_FIELDS:
        if key in data:
            out[key] = data[key]
    if "name" in out:
        out["name"] = limit_text(text(out["name"]), 200, "设备名称")
    for key, label, limit in (
        ("brand", "品牌", 100),
        ("model", "型号", 100),
        ("spec", "关键参数", 2000),
        ("note", "备注", 2000),
    ):
        if key in out:
            out[key] = limit_text(text(out[key]), limit, label)
    for key in ("currency", "vendor", "owner"):
        if key in out:
            out[key] = text(out[key])
    if "category" in out:
        out["category"] = _clean_category(out["category"], "other")
    if "status" in out:
        out["status"] = _clean_status(out["status"], "planned")
    if "unit" in out:
        out["unit"] = _clean_unit(out["unit"], "台")
    if "quantity" in out:
        out["quantity"] = _clean_quantity(out["quantity"], 1)
    if "unit_price" in out:
        out["unit_price"] = _clean_price(out["unit_price"])
    if "sort_order" in out:
        try:
            out["sort_order"] = float(out["sort_order"])
        except (TypeError, ValueError):
            out.pop("sort_order", None)
    if not partial and not out.get("name"):
        raise ApiError("设备名称不能为空", 400, "name_required")
    return out


def _device_row(device_id: str) -> dict:
    row = get_db().execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        raise ApiError("设备不存在", 404, "device_not_found")
    return dict(row)


def _diagram_row(diagram_id: str) -> dict:
    row = get_db().execute("SELECT * FROM diagrams WHERE id=?", (diagram_id,)).fetchone()
    if not row:
        raise ApiError("拓扑图不存在", 404, "diagram_not_found")
    return dict(row)


def _node_row(diagram_id: str, node_key: str) -> dict:
    row = get_db().execute(
        "SELECT * FROM diagram_nodes WHERE diagram_id=? AND node_key=?",
        (diagram_id, node_key),
    ).fetchone()
    if not row:
        raise ApiError("节点不存在，请先保存拓扑图", 404, "node_not_found")
    return dict(row)


def _link_dict(row) -> dict:
    return {
        "device_id": row["device_id"],
        "diagram_id": row["diagram_id"],
        "diagram_name": row["diagram_name"] if "diagram_name" in row.keys() else "",
        "node_key": row["node_key"],
        "node_label": row["node_label"] if "node_label" in row.keys() else row["node_key"],
        "quantity": row["quantity"] if "quantity" in row.keys() else 1,
        "note": row["note"] if "note" in row.keys() else "",
    }


def _links_for_device_ids(device_ids: list[str]) -> dict[str, list[dict]]:
    ids = [text(device_id) for device_id in device_ids if text(device_id)]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = get_db().execute(
        f"""SELECT l.device_id, l.diagram_id, l.node_key, l.quantity, l.note,
                   d.name AS diagram_name, dn.label AS node_label
            FROM device_node_links l
            JOIN diagrams d ON d.id=l.diagram_id
            LEFT JOIN diagram_nodes dn ON dn.diagram_id=l.diagram_id AND dn.node_key=l.node_key
            WHERE l.device_id IN ({placeholders})
            ORDER BY d.name, l.node_key""",
        ids,
    ).fetchall()
    out: dict[str, list[dict]] = {device_id: [] for device_id in ids}
    for row in rows:
        out.setdefault(row["device_id"], []).append(_link_dict(row))
    return out


def _device_dict(row, links: list[dict] | None = None) -> dict:
    data = dict(row)
    links = links or []
    data["category_label"] = CATEGORY_LABELS.get(data["category"], data["category"])
    data["status_label"] = STATUS_LABELS.get(data["status"], data["status"])
    price = data.get("unit_price")
    quantity = data.get("quantity") or 0
    data["total"] = round(quantity * price, 2) if price is not None else None
    data["linked_nodes"] = links
    data["linked_count"] = len(links)
    return data


def device_dict(device_id: str) -> dict:
    row = _device_row(device_id)
    links = _links_for_device_ids([device_id]).get(device_id, [])
    return _device_dict(row, links)


def _category_counts(project_id: str) -> list[dict]:
    rows = get_db().execute(
        "SELECT category, COUNT(*) AS n FROM devices WHERE project_id=? GROUP BY category",
        (project_id,),
    ).fetchall()
    counts = {row["category"]: row["n"] or 0 for row in rows}
    return [
        {"key": key, "label": CATEGORY_LABELS[key], "count": counts.get(key, 0)}
        for key in CATEGORIES
    ]


def device_summary(project_id: str) -> dict:
    ensure_project(project_id)
    db = get_db()
    devices = db.execute(
        "SELECT id, quantity, unit_price FROM devices WHERE project_id=?", (project_id,)
    ).fetchall()
    links = db.execute(
        """SELECT l.device_id, l.diagram_id, l.node_key
           FROM device_node_links l JOIN devices d ON d.id=l.device_id
           WHERE d.project_id=?""",
        (project_id,),
    ).fetchall()
    amount = 0.0
    quantity = 0
    for device in devices:
        quantity += device["quantity"] or 0
        if device["unit_price"] is not None:
            amount += (device["quantity"] or 0) * device["unit_price"]
    node_keys = {(link["diagram_id"], link["node_key"]) for link in links}
    return {
        "types": len(devices),
        "quantity": quantity,
        "linked_types": len({link["device_id"] for link in links}),
        "node_count": len(node_keys),
        "diagram_count": len({link["diagram_id"] for link in links}),
        "amount": round(amount, 2),
    }


def list_devices(
    project_id: str,
    category: str | None = None,
    status: str | None = None,
    q: str | None = None,
    linked: str | None = None,
) -> dict:
    ensure_project(project_id)
    clauses = ["project_id=?"]
    params: list = [project_id]
    category = text(category)
    if category and category != "all":
        clauses.append("category=?")
        params.append(_clean_category(category))
    status = text(status)
    if status and status != "all":
        clauses.append("status=?")
        params.append(_clean_status(status))
    keyword = text(q)
    if keyword:
        like = f"%{keyword}%"
        clauses.append("(name LIKE ? OR brand LIKE ? OR model LIKE ? OR spec LIKE ? OR note LIKE ?)")
        params.extend([like, like, like, like, like])
    linked = text(linked)
    if linked == "yes":
        clauses.append("EXISTS (SELECT 1 FROM device_node_links l WHERE l.device_id=devices.id)")
    elif linked == "no":
        clauses.append("NOT EXISTS (SELECT 1 FROM device_node_links l WHERE l.device_id=devices.id)")

    order = "CASE category " + " ".join(
        f"WHEN '{key}' THEN {index}" for key, index in CATEGORY_ORDER.items()
    ) + " ELSE 99 END, sort_order, name"
    rows = get_db().execute(
        f"SELECT * FROM devices WHERE {' AND '.join(clauses)} ORDER BY {order}", params
    ).fetchall()
    links_by_device = _links_for_device_ids([row["id"] for row in rows])
    items = [
        _device_dict(row, links_by_device.get(row["id"], []))
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "summary": device_summary(project_id),
        "categories": _category_counts(project_id),
        "statuses": [
            {"key": key, "label": STATUS_LABELS[key]} for key in STATUSES
        ],
    }


def device_links_for_diagram(diagram_id: str) -> dict[str, list[dict]]:
    """Node key -> linked device briefs (used by nodes_with_links)."""
    rows = get_db().execute(
        """SELECT l.device_id, l.diagram_id, l.node_key, l.quantity, l.note,
                  d.name, d.brand, d.model, d.category, d.status, d.unit,
                  d.quantity AS device_quantity
           FROM device_node_links l JOIN devices d ON d.id=l.device_id
           WHERE l.diagram_id=? ORDER BY d.sort_order, d.name""",
        (diagram_id,),
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["node_key"], []).append(
            {
                "device_id": row["device_id"],
                "id": row["device_id"],
                "name": row["name"],
                "brand": row["brand"],
                "model": row["model"],
                "category": row["category"],
                "category_label": CATEGORY_LABELS.get(row["category"], row["category"]),
                "status": row["status"],
                "status_label": STATUS_LABELS.get(row["status"], row["status"]),
                "quantity": row["quantity"],
                "unit": row["unit"],
                "device_quantity": row["device_quantity"],
                "note": row["note"],
            }
        )
    return out


def _normalise_links(links, project_id: str) -> list[dict]:
    if links is None:
        return []
    if not isinstance(links, list):
        raise ApiError("设备关联格式错误", 400, "invalid_links")
    db = get_db()
    out = []
    seen = set()
    for raw in links:
        if not isinstance(raw, dict):
            continue
        diagram_id = text(raw.get("diagram_id"))
        node_key = text(raw.get("node_key"))
        if not diagram_id or not node_key:
            continue
        key = (diagram_id, node_key)
        if key in seen:
            continue
        seen.add(key)
        diagram = db.execute("SELECT * FROM diagrams WHERE id=?", (diagram_id,)).fetchone()
        if not diagram:
            raise ApiError("拓扑图不存在", 404, "diagram_not_found")
        if diagram["project_id"] != project_id:
            raise ApiError("拓扑图与设备不属于同一项目", 400, "project_mismatch")
        node = db.execute(
            "SELECT node_key FROM diagram_nodes WHERE diagram_id=? AND node_key=?",
            (diagram_id, node_key),
        ).fetchone()
        if not node:
            raise ApiError("节点不存在，请先保存拓扑图", 404, "node_not_found")
        out.append(
            {
                "diagram_id": diagram_id,
                "node_key": node_key,
                "quantity": _clean_quantity(raw.get("quantity"), 1),
                "note": text(raw.get("note")),
            }
        )
    return out


def _touch_device(device_id: str, now: str):
    get_db().execute("UPDATE devices SET updated_at=? WHERE id=?", (now, device_id))


def _replace_links(device_id: str, project_id: str, links) -> None:
    db = get_db()
    normalised = _normalise_links(links, project_id)
    now = utcnow()
    db.execute("DELETE FROM device_node_links WHERE device_id=?", (device_id,))
    for link in normalised:
        db.execute(
            """INSERT INTO device_node_links
               (device_id, diagram_id, node_key, quantity, note, created_at)
               VALUES (?,?,?,?,?,?)""",
            (device_id, link["diagram_id"], link["node_key"], link["quantity"], link["note"], now),
        )
    _touch_device(device_id, now)


def create_device_record(project_id: str, data: dict) -> str:
    ensure_project(project_id)
    fields = clean_device_payload(data)
    db = get_db()
    device_id = new_id("d_")
    now = utcnow()
    if "sort_order" not in fields:
        row = db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM devices WHERE project_id=?",
            (project_id,),
        ).fetchone()
        fields["sort_order"] = float(row["n"])
    fields.setdefault("category", "other")
    fields.setdefault("brand", "")
    fields.setdefault("model", "")
    fields.setdefault("spec", "")
    fields.setdefault("quantity", 1)
    fields.setdefault("unit", "台")
    fields.setdefault("status", "planned")
    fields.setdefault("currency", "CNY")
    fields.setdefault("vendor", "")
    fields.setdefault("owner", "")
    fields.setdefault("note", "")
    db.execute(
        """INSERT INTO devices
           (id, project_id, name, category, brand, model, spec, quantity, unit, status,
            unit_price, currency, vendor, owner, note, sort_order, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            device_id, project_id, fields["name"], fields["category"], fields["brand"],
            fields["model"], fields["spec"], fields["quantity"], fields["unit"],
            fields["status"], fields.get("unit_price"), fields["currency"],
            fields["vendor"], fields["owner"], fields["note"], fields["sort_order"],
            now, now,
        ),
    )
    if "links" in data:
        _replace_links(device_id, project_id, data.get("links"))
    log_activity(project_id, "device", device_id, "create", fields["name"])
    return device_id


def update_device_record(device_id: str, data: dict) -> dict:
    device = _device_row(device_id)
    project_id = device["project_id"]
    fields = clean_device_payload(data, partial=True)
    if not fields and "links" not in data:
        raise ApiError("没有要更新的字段", 400, "empty_patch")
    db = get_db()
    if fields:
        fields["updated_at"] = utcnow()
        sets = ", ".join(f"{key}=?" for key in fields)
        db.execute(f"UPDATE devices SET {sets} WHERE id=?", [*fields.values(), device_id])
    if "links" in data:
        _replace_links(device_id, project_id, data.get("links"))
    log_activity(project_id, "device", device_id, "update", fields.get("name", device["name"]))
    return device_dict(device_id)


def delete_device_record(device_id: str) -> dict:
    device = _device_row(device_id)
    db = get_db()
    db.execute("DELETE FROM devices WHERE id=?", (device_id,))
    log_activity(device["project_id"], "device", device_id, "delete", device["name"])
    return {"deleted": True, "id": device_id, "name": device["name"]}


def _validate_node(device: dict, diagram_id: str, node_key: str) -> None:
    diagram = _diagram_row(diagram_id)
    if diagram["project_id"] != device["project_id"]:
        raise ApiError("设备与拓扑图不属于同一项目", 400, "project_mismatch")
    _node_row(diagram_id, node_key)


def link_device_to_node(
    device_id: str, diagram_id: str, node_key: str, quantity=None, note: str = ""
) -> dict:
    device = _device_row(device_id)
    _validate_node(device, diagram_id, node_key)
    db = get_db()
    now = utcnow()
    link_quantity = device["quantity"] if quantity in (None, "") else _clean_quantity(quantity, 1)
    db.execute(
        """INSERT INTO device_node_links
           (device_id, diagram_id, node_key, quantity, note, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(device_id, diagram_id, node_key)
           DO UPDATE SET quantity=excluded.quantity, note=excluded.note""",
        (device_id, diagram_id, node_key, link_quantity, text(note), now),
    )
    _touch_device(device_id, now)
    log_activity(
        device["project_id"], "device", device_id, "link",
        f"{diagram_id}:{node_key}",
    )
    return device_dict(device_id)


def unlink_device_from_node(device_id: str, diagram_id: str, node_key: str) -> dict:
    device = _device_row(device_id)
    cur = get_db().execute(
        "DELETE FROM device_node_links WHERE device_id=? AND diagram_id=? AND node_key=?",
        (device_id, diagram_id, node_key),
    )
    if cur.rowcount == 0:
        raise ApiError("设备关联不存在", 404, "device_link_not_found")
    _touch_device(device_id, utcnow())
    log_activity(
        device["project_id"], "device", device_id, "unlink",
        f"{diagram_id}:{node_key}",
    )
    return device_dict(device_id)


def create_device_and_link(diagram_id: str, node_key: str, data: dict) -> str:
    diagram = _diagram_row(diagram_id)
    _node_row(diagram_id, node_key)
    payload = data if isinstance(data, dict) else {}
    device_id = create_device_record(diagram["project_id"], payload)
    link_device_to_node(
        device_id, diagram_id, node_key,
        quantity=payload.get("quantity", 1),
    )
    return device_id


def export_devices_csv(project_id: str) -> tuple[str, str]:
    ensure_project(project_id)
    db = get_db()
    project = db.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()
    devices = db.execute(
        """SELECT * FROM devices WHERE project_id=?
           ORDER BY CASE category
             WHEN 'server' THEN 0 WHEN 'storage' THEN 1 WHEN 'network' THEN 2
             WHEN 'security' THEN 3 WHEN 'software' THEN 4 ELSE 5 END,
             sort_order, name""",
        (project_id,),
    ).fetchall()
    links_by_device = _links_for_device_ids([row["id"] for row in devices])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "设备名称", "类别", "品牌", "型号", "关键参数", "数量", "单位", "状态",
        "单价", "小计", "供应商", "负责人", "备注", "关联拓扑",
    ])
    for row in devices:
        links = links_by_device.get(row["id"], [])
        linked = "; ".join(
            f"{link['diagram_name'] or link['diagram_id']} / {link['node_label']} ×{link['quantity']}"
            for link in links
        )
        price = row["unit_price"]
        total = round((row["quantity"] or 0) * price, 2) if price is not None else ""
        writer.writerow([
            csv_safe(row["name"]),
            csv_safe(CATEGORY_LABELS.get(row["category"], row["category"])),
            csv_safe(row["brand"]),
            csv_safe(row["model"]),
            csv_safe(row["spec"]),
            row["quantity"],
            csv_safe(row["unit"]),
            csv_safe(STATUS_LABELS.get(row["status"], row["status"])),
            "" if price is None else f"{price:.2f}",
            "" if total == "" else f"{total:.2f}",
            csv_safe(row["vendor"]),
            csv_safe(row["owner"]),
            csv_safe(row["note"]),
            csv_safe(linked),
        ])
    filename = f"设备清单-{(project['name'] if project else '项目')}.csv"
    filename = filename.replace("/", "_").replace("\\", "_")
    return filename, "\ufeff" + buffer.getvalue()


def export_filename_header(filename: str) -> str:
    return "attachment; filename*=UTF-8''" + quote(filename)


# ---------------------------------------------------------------------------
# Global device templates
# ---------------------------------------------------------------------------
TEMPLATE_FIELDS = ("name", "category", "brand", "model", "spec", "unit", "unit_price", "note")

CATEGORY_ALIASES = {key: key for key in CATEGORIES}
CATEGORY_ALIASES.update({label: key for key, label in CATEGORY_LABELS.items()})
CATEGORY_ALIASES.update({"网络设备": "network", "安全设备": "security", "软件许可": "software"})

TEMPLATE_HEADERS = ["类别", "品牌", "型号", "关键参数", "单位", "参考单价", "备注"]
HEADER_ALIASES = {
    "设备名称": "name", "名称": "name", "name": "name",
    "类别": "category", "category": "category",
    "品牌": "brand", "brand": "brand",
    "型号": "model", "model": "model",
    "关键参数": "spec", "参数": "spec", "规格": "spec", "spec": "spec",
    "单位": "unit", "默认单位": "unit", "unit": "unit",
    "参考单价": "unit_price", "单价": "unit_price", "unit_price": "unit_price",
    "备注": "note", "note": "note",
}


def _category_from_text(value, fallback: str = "other") -> str:
    value = text(value)
    return CATEGORY_ALIASES.get(value, fallback)


def _template_default_name(model, brand, category: str, spec) -> str:
    """Templates no longer ask for a device name; keep a hidden label for pickers."""
    model, brand = text(model), text(brand)
    if model:
        return model
    if brand:
        return brand
    label = CATEGORY_LABELS.get(category or "server", "设备")
    first_line = text(spec).splitlines()[0][:24] if text(spec) else ""
    return f"{label} {first_line}".strip() or "设备模板"


def _template_display_label(name, brand, model, category="other", spec="") -> str:
    base = " ".join(part for part in (text(brand), text(model)) if part).strip()
    if base:
        return base
    if text(name):
        return text(name)
    return _template_default_name(model, brand, category, spec)


def _clean_template_payload(data: dict, partial: bool = False) -> dict:
    out = {}
    for key in TEMPLATE_FIELDS:
        if key in data:
            out[key] = data[key]
    if "name" in out:
        out["name"] = limit_text(text(out["name"]), 200, "模板名称")
        if not out["name"]:
            out.pop("name")
    for key, label, limit in (
        ("brand", "品牌", 100),
        ("model", "型号", 100),
        ("spec", "关键参数", 2000),
        ("note", "备注", 2000),
    ):
        if key in out:
            out[key] = limit_text(text(out[key]), limit, label)
    if "category" in out:
        out["category"] = _category_from_text(out["category"], "server")
    if "unit" in out:
        out["unit"] = _clean_unit(out["unit"], "台")
    if "unit_price" in out:
        raw = out["unit_price"]
        if isinstance(raw, str):
            raw = raw.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").strip()
        out["unit_price"] = _clean_price(raw)
    return out


def _template_row(template_id: str) -> dict:
    row = get_db().execute(
        "SELECT * FROM device_templates WHERE id=?", (template_id,)
    ).fetchone()
    if not row:
        raise ApiError("设备模板不存在", 404, "template_not_found")
    return dict(row)


def _template_dict(row) -> dict:
    data = dict(row)
    data["category_label"] = CATEGORY_LABELS.get(data["category"], data["category"])
    data["display_label"] = _template_display_label(
        data.get("name"), data.get("brand"), data.get("model"),
        data.get("category"), data.get("spec"),
    )
    return data


def list_device_templates(
    category: str | None = None, q: str | None = None, brand: str | None = None
) -> dict:
    clauses = []
    params: list = []
    category = text(category)
    if category and category != "all":
        clauses.append("category=?")
        params.append(_category_from_text(category))
    brand = text(brand)
    if brand and brand != "all":
        clauses.append("brand=?")
        params.append(brand)
    keyword = text(q)
    if keyword:
        like = f"%{keyword}%"
        clauses.append("(name LIKE ? OR brand LIKE ? OR model LIKE ? OR spec LIKE ? OR note LIKE ?)")
        params.extend([like, like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    db = get_db()
    rows = db.execute(
        f"SELECT * FROM device_templates {where} ORDER BY updated_at DESC, name", params
    ).fetchall()
    counts = {
        row["category"]: row["n"] or 0
        for row in db.execute(
            "SELECT category, COUNT(*) AS n FROM device_templates GROUP BY category"
        )
    }
    brands = [
        row["brand"] for row in db.execute(
            "SELECT DISTINCT brand FROM device_templates WHERE brand!='' ORDER BY brand"
        )
    ]
    total_row = db.execute("SELECT COUNT(*) AS n, MAX(updated_at) AS updated_at FROM device_templates").fetchone()
    items = [_template_dict(row) for row in rows]
    return {
        "items": items,
        "total": len(items),
        "summary": {
            "total": total_row["n"] or 0,
            "categories": sum(1 for key in CATEGORIES if counts.get(key)),
            "brands": len(brands),
            "updated_at": total_row["updated_at"],
        },
        "categories": [
            {"key": key, "label": CATEGORY_LABELS[key], "count": counts.get(key, 0)}
            for key in CATEGORIES
        ],
        "brands": brands,
    }


def create_device_template(data: dict) -> dict:
    fields = _clean_template_payload(data)
    category = fields.get("category", "server")
    brand = fields.get("brand", "")
    model = fields.get("model", "")
    name = fields.get("name") or _template_default_name(model, brand, category, fields.get("spec", ""))
    db = get_db()
    existing = _template_duplicate(name, brand, model)
    if existing:
        raise ApiError("相同品牌、型号的模板已存在", 409, "template_duplicate")
    template_id = new_id("tpl_")
    now = utcnow()
    try:
        db.execute(
            """INSERT INTO device_templates
               (id, name, category, brand, model, spec, unit, unit_price, note, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                template_id, name, category,
                brand, model, fields.get("spec", ""),
                fields.get("unit", "台"), fields.get("unit_price"), fields.get("note", ""),
                now, now,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise ApiError("相同品牌、型号的模板已存在", 409, "template_duplicate") from exc
    return _template_dict(_template_row(template_id))


def update_device_template(template_id: str, data: dict) -> dict:
    current = _template_row(template_id)
    fields = _clean_template_payload(data, partial=True)
    if not fields:
        raise ApiError("没有要更新的字段", 400, "empty_patch")
    brand = fields.get("brand", current["brand"])
    model = fields.get("model", current["model"])
    duplicate = _template_duplicate(fields.get("name", current["name"]), brand, model)
    if duplicate and duplicate["id"] != template_id:
        raise ApiError("相同品牌、型号的模板已存在", 409, "template_duplicate")
    db = get_db()
    fields["updated_at"] = utcnow()
    sets = ", ".join(f"{key}=?" for key in fields)
    try:
        db.execute(
            f"UPDATE device_templates SET {sets} WHERE id=?",
            [*fields.values(), template_id],
        )
    except sqlite3.IntegrityError as exc:
        raise ApiError("相同品牌、型号的模板已存在", 409, "template_duplicate") from exc
    return _template_dict(_template_row(template_id))


def delete_device_template(template_id: str) -> dict:
    row = _template_row(template_id)
    get_db().execute("DELETE FROM device_templates WHERE id=?", (template_id,))
    return {"deleted": True, "id": template_id, "name": row["name"]}


def template_sample_csv() -> tuple[str, str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(TEMPLATE_HEADERS)
    return "设备模板导入模板.csv", "\ufeff" + buffer.getvalue()


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApiError("CSV 编码无法识别，请使用 UTF-8 或 GBK", 400, "invalid_encoding")


def _parse_template_csv(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ApiError("CSV 缺少表头", 400, "csv_header_required")
    mapping = {}
    for header in reader.fieldnames:
        key = HEADER_ALIASES.get(text(header).replace("\ufeff", ""))
        if key:
            mapping[key] = header
    rows = []
    for index, raw in enumerate(reader, start=2):
        data = {}
        for key, header in mapping.items():
            data[key] = raw.get(header, "")
        brand = text(data.get("brand"))
        model = text(data.get("model"))
        if not any(
            text(data.get(key))
            for key in ("name", "category", "brand", "model", "spec", "unit", "unit_price", "note")
        ):
            continue
        category = _category_from_text(data.get("category"), "server")
        name = text(data.get("name")) or _template_default_name(
            model, brand, category, data.get("spec")
        )
        error = ""
        price_raw = text(data.get("unit_price"))
        price = None
        if price_raw:
            cleaned = price_raw.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").strip()
            try:
                price = max(0.0, float(cleaned))
            except ValueError:
                error = "参考单价不是数字"
        rows.append(
            {
                "row": index,
                "name": name,
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, "其他"),
                "brand": brand,
                "model": model,
                "spec": text(data.get("spec")),
                "unit": _clean_unit(data.get("unit"), "台"),
                "unit_price": price,
                "note": text(data.get("note")),
                "error": error,
            }
        )
    return rows


def _template_duplicate(name: str, brand: str, model: str):
    db = get_db()
    if brand or model:
        row = db.execute(
            "SELECT * FROM device_templates WHERE brand=? AND model=? LIMIT 1",
            (brand, model),
        ).fetchone()
        if row:
            return row
    return db.execute(
        "SELECT * FROM device_templates WHERE name=? AND brand=? AND model=?",
        (name, brand, model),
    ).fetchone()


def preview_template_csv(raw: bytes) -> dict:
    rows = _parse_template_csv(_decode_csv(raw))
    items = []
    new_count = duplicate_count = invalid_count = 0
    for row in rows:
        if row["error"]:
            row["status"] = "invalid"
            invalid_count += 1
        elif _template_duplicate(row["name"], row["brand"], row["model"]):
            row["status"] = "duplicate"
            duplicate_count += 1
        else:
            row["status"] = "new"
            new_count += 1
        items.append(row)
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "new": new_count,
            "duplicate": duplicate_count,
            "invalid": invalid_count,
        },
    }


def import_template_csv(raw: bytes, mode: str = "skip") -> dict:
    rows = _parse_template_csv(_decode_csv(raw))
    mode = "overwrite" if mode == "overwrite" else "skip"
    imported = updated = skipped = invalid = 0
    errors = []
    db = get_db()
    now = utcnow()
    for row in rows:
        if row["error"]:
            invalid += 1
            errors.append({"row": row["row"], "message": row["error"]})
            continue
        existing = _template_duplicate(row["name"], row["brand"], row["model"])
        if existing:
            if mode == "skip":
                skipped += 1
                continue
            db.execute(
                """UPDATE device_templates
                   SET category=?, spec=?, unit=?, unit_price=?, note=?, updated_at=?
                   WHERE id=?""",
                (
                    row["category"], row["spec"], row["unit"], row["unit_price"],
                    row["note"], now, existing["id"],
                ),
            )
            updated += 1
            continue
        db.execute(
            """INSERT INTO device_templates
               (id, name, category, brand, model, spec, unit, unit_price, note, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                new_id("tpl_"), row["name"], row["category"], row["brand"], row["model"],
                row["spec"], row["unit"], row["unit_price"], row["note"], now, now,
            ),
        )
        imported += 1
    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "invalid": invalid,
        "errors": errors,
        "summary": {"total": len(rows), "imported": imported, "updated": updated,
                    "skipped": skipped, "invalid": invalid},
    }
