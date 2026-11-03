"""Diagram + node endpoints."""
from __future__ import annotations

import copy

from flask import Blueprint, jsonify, request

from db import ApiError, dumps, get_db, new_id, utcnow
from services import (
    content_of,
    create_task_record,
    diagram_dict,
    ensure_project,
    log_activity,
    merge_followup_into_content,
    nodes_with_links,
    sync_diagram_nodes,
    text,
)

bp = Blueprint("diagrams", __name__, url_prefix="/api/diagrams")

EMPTY_CONTENT = {
    "app": "topotash",
    "version": 2,
    "shapes": {},
    "order": [],
    "groups": {},
    "imagePool": {},
}

KINDS = ("topology", "architecture", "deployment", "other")


def _get_diagram(diagram_id: str):
    row = get_db().execute("SELECT * FROM diagrams WHERE id=?", (diagram_id,)).fetchone()
    if not row:
        raise ApiError(f"拓扑图不存在：{diagram_id}", 404, "diagram_not_found")
    return row


def _clean_kind(value, fallback: str = "topology") -> str:
    value = text(value)
    return value if value in KINDS else fallback


def _node_count(content: dict) -> int:
    return len([s for s in (content.get("shapes") or {}).values()
                if isinstance(s, dict) and s.get("type") == "shape"])


def _normalise_content(content) -> dict:
    """Validate a canvas document and strip runtime-only metadata."""
    if not isinstance(content, dict) or not isinstance(content.get("shapes"), dict):
        raise ApiError("内容格式错误：需要画布 JSON（含 shapes 对象）", 400, "invalid_content")
    content = copy.deepcopy(content)
    content.pop("_topotash", None)
    for shape in content["shapes"].values():
        if isinstance(shape, dict):
            shape.pop("tt", None)
    content["app"] = text(content.get("app")) or "topotash"
    content["version"] = content.get("version") or 2
    if not isinstance(content.get("order"), list):
        content["order"] = list(content["shapes"].keys())
    if not isinstance(content.get("groups"), dict):
        content["groups"] = {}
    if not isinstance(content.get("imagePool"), dict):
        content["imagePool"] = {}
    return content


def _unique_diagram_name(project_id: str | None, base: str, suffix: str = "") -> str:
    db = get_db()
    base = (text(base) or "未命名拓扑图")[:200]
    candidate = f"{base}{suffix}"
    n = 2
    while db.execute(
        "SELECT 1 FROM diagrams WHERE project_id IS ? AND name=?", (project_id, candidate)
    ).fetchone():
        candidate = f"{base}{suffix} ({n})"
        n += 1
    return candidate[:200]


def _create_diagram_record(
    project_id: str | None, name: str, kind: str, description: str, content: dict
) -> str:
    """Insert a diagram + node index. Caller commits."""
    db = get_db()
    did = new_id("d_")
    now = utcnow()
    db.execute(
        """INSERT INTO diagrams
           (id, project_id, name, kind, description, content_json, version, node_count, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            did, project_id, name, _clean_kind(kind), text(description), dumps(content), 1,
            _node_count(content), now, now,
        ),
    )
    sync_diagram_nodes(did, content)
    if project_id:
        log_activity(project_id, "diagram", did, "create", name)
    return did


def _diagram_with_counts(row) -> dict:
    db = get_db()
    d = diagram_dict(row)
    d["followup_count"] = db.execute(
        "SELECT COUNT(*) AS n FROM diagram_nodes WHERE diagram_id=? AND followup_status IN ('todo','doing')",
        (row["id"],),
    ).fetchone()["n"]
    d["linked_task_count"] = db.execute(
        "SELECT COUNT(DISTINCT task_id) AS n FROM node_task_links WHERE diagram_id=?", (row["id"],)
    ).fetchone()["n"]
    d["task_link_count"] = db.execute(
        "SELECT COUNT(*) AS n FROM task_diagrams WHERE diagram_id=?", (row["id"],)
    ).fetchone()["n"]
    return d


@bp.get("")
def list_diagrams():
    db = get_db()
    clauses = []
    args = []
    project_id = request.args.get("project_id")
    unbound = request.args.get("unbound") in ("1", "true", "yes")
    if unbound:
        clauses.append("project_id IS NULL")
    elif project_id:
        clauses.append("project_id=?")
        args.append(project_id)
    q = text(request.args.get("q"))
    if q:
        clauses.append("name LIKE ?")
        args.append(f"%{q}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(f"SELECT * FROM diagrams {where} ORDER BY updated_at DESC", args).fetchall()
    items = []
    for r in rows:
        d = _diagram_with_counts(r)
        project = db.execute("SELECT name FROM projects WHERE id=?", (r["project_id"],)).fetchone()
        d["project_name"] = project["name"] if project else ""
        items.append(d)
    return jsonify({"items": items, "total": len(items)})


@bp.post("")
def create_diagram():
    data = request.get_json(silent=True) or {}
    project_id = text(data.get("project_id")) or None
    if project_id:
        ensure_project(project_id)
    name = text(data.get("name")) or "未命名拓扑图"
    content = data.get("content")
    if isinstance(content, dict) and isinstance(content.get("shapes"), dict):
        content = _normalise_content(content)
    else:
        content = copy.deepcopy(EMPTY_CONTENT)
    did = _create_diagram_record(
        project_id, name, text(data.get("kind")), text(data.get("description")), content
    )
    get_db().commit()
    return jsonify(_diagram_with_counts(_get_diagram(did))), 201


def _import_diagram_name(source_name: str) -> str:
    name = text(source_name).replace("\\", "/").rsplit("/", 1)[-1]
    for suffix in (".vweb.json", ".json"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", " ").strip() or "导入的拓扑图"


@bp.post("/import")
def import_diagram():
    """Import a canvas JSON file (e.g. an editor-exported ``.vweb.json``)."""
    data = request.get_json(silent=True) or {}
    project_id = text(data.get("project_id")) or None
    if project_id:
        ensure_project(project_id)
    content = _normalise_content(data.get("content"))
    source_name = text(data.get("source_name"))
    name = _unique_diagram_name(
        project_id, text(data.get("name")) or _import_diagram_name(source_name)
    )
    description = text(data.get("description"))
    if not description and source_name:
        description = f"从 {source_name} 导入"
    did = _create_diagram_record(
        project_id, name, text(data.get("kind")), description, content
    )
    get_db().commit()
    return jsonify(_diagram_with_counts(_get_diagram(did))), 201


@bp.post("/<diagram_id>/duplicate")
def duplicate_diagram(diagram_id):
    """Copy a diagram (canvas + node index); task links are not copied."""
    row = _get_diagram(diagram_id)
    data = request.get_json(silent=True) or {}
    target_project = text(data.get("project_id")) or row["project_id"]
    if target_project:
        ensure_project(target_project)
    raw_name = text(data.get("name"))
    if raw_name:
        name = _unique_diagram_name(target_project, raw_name)
    else:
        name = _unique_diagram_name(target_project, row["name"], " 副本")
    content = _normalise_content(content_of(row))
    did = _create_diagram_record(
        target_project, name, row["kind"], row["description"], content
    )
    get_db().commit()
    return jsonify(_diagram_with_counts(_get_diagram(did))), 201


@bp.get("/<diagram_id>")
def get_diagram(diagram_id):
    row = _get_diagram(diagram_id)
    data = _diagram_with_counts(row)
    data["nodes"] = nodes_with_links(diagram_id)
    project = get_db().execute("SELECT name FROM projects WHERE id=?", (row["project_id"],)).fetchone()
    data["project_name"] = project["name"] if project else ""
    data["task_links"] = [
        dict(r)
        for r in get_db().execute(
            """SELECT td.*, t.title, t.status, t.stage FROM task_diagrams td
               JOIN tasks t ON t.id=td.task_id WHERE td.diagram_id=? ORDER BY t.created_at""",
            (diagram_id,),
        ).fetchall()
    ]
    return jsonify(data)


def _drop_cross_project_links(diagram_id: str, project_id: str) -> None:
    """Remove task links that no longer belong to the diagram's project."""
    db = get_db()
    affected = [
        r["node_key"]
        for r in db.execute(
            """SELECT DISTINCT l.node_key FROM node_task_links l
               JOIN tasks t ON t.id = l.task_id
               WHERE l.diagram_id=? AND t.project_id!=?""",
            (diagram_id, project_id),
        ).fetchall()
    ]
    db.execute(
        """DELETE FROM node_task_links WHERE diagram_id=?
           AND task_id IN (SELECT id FROM tasks WHERE project_id!=?)""",
        (diagram_id, project_id),
    )
    db.execute(
        """DELETE FROM task_diagrams WHERE diagram_id=?
           AND task_id IN (SELECT id FROM tasks WHERE project_id!=?)""",
        (diagram_id, project_id),
    )
    for node_key in affected:
        remaining = db.execute(
            "SELECT 1 FROM node_task_links WHERE diagram_id=? AND node_key=? LIMIT 1",
            (diagram_id, node_key),
        ).fetchone()
        if not remaining:
            db.execute(
                "UPDATE diagram_nodes SET followup_status='none' WHERE diagram_id=? AND node_key=?",
                (diagram_id, node_key),
            )


@bp.patch("/<diagram_id>")
def patch_diagram(diagram_id):
    row = _get_diagram(diagram_id)
    data = request.get_json(silent=True) or {}
    fields = {}
    for key in ("name", "description"):
        if key in data:
            fields[key] = text(data[key])
    if "kind" in data:
        fields["kind"] = _clean_kind(data["kind"], row["kind"])
    project_changed = False
    old_project_id = row["project_id"]
    if "project_id" in data:
        project_id = text(data["project_id"])
        if not project_id:
            raise ApiError("缺少 project_id", 400, "project_required")
        ensure_project(project_id)
        if project_id != old_project_id:
            fields["project_id"] = project_id
            project_changed = True
    if not fields:
        raise ApiError("没有要更新的字段", 400, "empty_patch")
    if "name" in fields and not fields["name"]:
        raise ApiError("拓扑图名称不能为空", 400, "name_required")
    fields["updated_at"] = utcnow()
    db = get_db()
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE diagrams SET {sets} WHERE id=?", [*fields.values(), diagram_id])
    if project_changed:
        new_project_id = fields["project_id"]
        _drop_cross_project_links(diagram_id, new_project_id)
        old = db.execute("SELECT name FROM projects WHERE id=?", (old_project_id,)).fetchone() if old_project_id else None
        new = db.execute("SELECT name FROM projects WHERE id=?", (new_project_id,)).fetchone()
        if old_project_id:
            log_activity(
                old_project_id, "diagram", diagram_id, "update",
                f"从项目「{old['name'] if old else old_project_id}」移出",
            )
        log_activity(
            new_project_id, "diagram", diagram_id, "update",
            f"绑定到项目「{new['name'] if new else new_project_id}」",
        )
    db.commit()
    data = _diagram_with_counts(_get_diagram(diagram_id))
    project = get_db().execute(
        "SELECT name FROM projects WHERE id=?", (data["project_id"],)
    ).fetchone()
    data["project_name"] = project["name"] if project else ""
    return jsonify(data)


@bp.delete("/<diagram_id>")
def delete_diagram(diagram_id):
    row = _get_diagram(diagram_id)
    get_db().execute("DELETE FROM diagrams WHERE id=?", (diagram_id,))
    get_db().commit()
    return jsonify({"deleted": True, "id": diagram_id, "name": row["name"]})


# ---------------------------------------------------------------------------
# Canvas content (TopoTash canvas JSON)
# ---------------------------------------------------------------------------
@bp.get("/<diagram_id>/content")
def get_content(diagram_id):
    row = _get_diagram(diagram_id)
    content = content_of(row)
    content = merge_followup_into_content(diagram_id, content)
    project = get_db().execute("SELECT * FROM projects WHERE id=?", (row["project_id"],)).fetchone()
    content["_topotash"] = {
        "diagramId": row["id"],
        "diagramName": row["name"],
        "projectId": row["project_id"],
        "projectName": project["name"] if project else "",
        "stage": project["stage"] if project else "research",
        "version": row["version"],
        "nodeCount": row["node_count"],
    }
    return jsonify(content)


@bp.put("/<diagram_id>/content")
def put_content(diagram_id):
    row = _get_diagram(diagram_id)
    data = request.get_json(silent=True) or {}
    content = data.get("content") if isinstance(data.get("content"), dict) else data
    if not isinstance(content, dict) or not isinstance(content.get("shapes"), dict):
        raise ApiError("内容格式错误：需要画布 JSON（含 shapes 对象）", 400, "invalid_content")
    # tt 是 TopoTash 注入的运行时元数据，不写回文件
    for shape in content["shapes"].values():
        if isinstance(shape, dict):
            shape.pop("tt", None)
    content.pop("_topotash", None)
    content.setdefault("app", "topotash")
    content.setdefault("version", 2)
    now = utcnow()
    db = get_db()
    db.execute(
        "UPDATE diagrams SET content_json=?, version=version+1, node_count=?, updated_at=? WHERE id=?",
        (dumps(content), len([s for s in content["shapes"].values() if isinstance(s, dict) and s.get("type") == "shape"]), now, diagram_id),
    )
    count = sync_diagram_nodes(diagram_id, content)
    db.commit()
    return jsonify(
        {
            "saved": True,
            "diagram_id": diagram_id,
            "version": row["version"] + 1,
            "node_count": count,
            "updated_at": now,
        }
    )


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
@bp.get("/<diagram_id>/nodes")
def list_nodes(diagram_id):
    _get_diagram(diagram_id)
    return jsonify({"items": nodes_with_links(diagram_id)})


@bp.patch("/<diagram_id>/nodes/<node_key>")
def patch_node(diagram_id, node_key):
    _get_diagram(diagram_id)
    db = get_db()
    row = db.execute(
        "SELECT * FROM diagram_nodes WHERE diagram_id=? AND node_key=?", (diagram_id, node_key)
    ).fetchone()
    if not row:
        raise ApiError("节点不存在", 404, "node_not_found")
    data = request.get_json(silent=True) or {}
    fields = {}
    if "note" in data:
        fields["note"] = text(data["note"])
    if "label" in data:
        fields["label"] = text(data["label"]) or row["label"]
    if "followup_status" in data:
        status = text(data["followup_status"])
        if status not in ("none", "todo", "doing", "done"):
            raise ApiError("无效的跟进状态", 400, "invalid_status")
        fields["followup_status"] = status
    if not fields:
        raise ApiError("没有要更新的字段", 400, "empty_patch")
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(
        f"UPDATE diagram_nodes SET {sets} WHERE diagram_id=? AND node_key=?",
        [*fields.values(), diagram_id, node_key],
    )
    db.commit()
    node = next((n for n in nodes_with_links(diagram_id) if n["node_key"] == node_key), None)
    return jsonify(node)


def _followup_node(diagram_id: str, node_key: str) -> dict:
    node = next((n for n in nodes_with_links(diagram_id) if n["node_key"] == node_key), None)
    if not node:
        raise ApiError("节点不存在", 404, "node_not_found")
    return node


@bp.post("/<diagram_id>/nodes/<node_key>/followup")
def set_followup(diagram_id, node_key):
    diagram = _get_diagram(diagram_id)
    db = get_db()
    node = db.execute(
        "SELECT * FROM diagram_nodes WHERE diagram_id=? AND node_key=?", (diagram_id, node_key)
    ).fetchone()
    if not node:
        raise ApiError("节点不存在，请先保存拓扑图", 404, "node_not_found")
    data = request.get_json(silent=True) or {}
    task = None
    task_id = text(data.get("task_id"))
    create = data.get("create_task")

    if create:
        payload = create if isinstance(create, dict) else {}
        title = text(payload.get("title")) or f"跟进：{node['label']}"
        tid = create_task_record(
            diagram["project_id"],
            {
                "title": title,
                "description": text(payload.get("description"))
                or f"由拓扑图《{diagram['name']}》节点「{node['label']}」创建。",
                "priority": payload.get("priority", 2),
                "status": payload.get("status", "todo"),
                "stage": payload.get("stage") or _project_stage(diagram["project_id"]),
                "due_date": payload.get("due_date"),
                "source": "diagram",
                "tags": payload.get("tags") or ["拓扑跟进"],
            },
            source="diagram",
        )
        task_id = tid
        task = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()

    if task_id:
        task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ApiError("任务不存在", 404, "task_not_found")
        if task["project_id"] != diagram["project_id"]:
            raise ApiError("任务与拓扑图不属于同一项目", 400, "project_mismatch")
        db.execute(
            "UPDATE node_task_links SET is_primary=0 WHERE diagram_id=? AND node_key=?",
            (diagram_id, node_key),
        )
        db.execute(
            """INSERT INTO node_task_links
               (diagram_id, node_key, task_id, relation, is_primary, note, created_at)
               VALUES (?,?,?,?,1,?,?)
               ON CONFLICT(diagram_id, node_key, task_id)
               DO UPDATE SET is_primary=1""",
            (diagram_id, node_key, task_id, text(data.get("relation")) or "followup",
             text(data.get("note")), utcnow()),
        )
        status = task["status"]
    else:
        status = text(data.get("status")) or node["followup_status"]
        if status not in ("none", "todo", "doing", "done"):
            raise ApiError("无效的跟进状态", 400, "invalid_status")

    db.execute(
        "UPDATE diagram_nodes SET followup_status=?, note=? WHERE diagram_id=? AND node_key=?",
        (status, text(data.get("note", node["note"])), diagram_id, node_key),
    )
    if status != "none":
        log_activity(
            diagram["project_id"], "node", f"{diagram_id}:{node_key}", "update",
            f"{node['label']} → {status}",
        )
    db.commit()
    out = {"node": _followup_node(diagram_id, node_key)}
    if task:
        out["task"] = dict(task)
    return jsonify(out)


def _project_stage(project_id: str) -> str:
    row = get_db().execute("SELECT stage FROM projects WHERE id=?", (project_id,)).fetchone()
    return row["stage"] if row else "research"


@bp.post("/<diagram_id>/nodes/<node_key>/links")
def add_node_link(diagram_id, node_key):
    diagram = _get_diagram(diagram_id)
    db = get_db()
    node = db.execute(
        "SELECT * FROM diagram_nodes WHERE diagram_id=? AND node_key=?", (diagram_id, node_key)
    ).fetchone()
    if not node:
        raise ApiError("节点不存在", 404, "node_not_found")
    data = request.get_json(silent=True) or {}
    task_id = text(data.get("task_id"))
    task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise ApiError("任务不存在", 404, "task_not_found")
    if task["project_id"] != diagram["project_id"]:
        raise ApiError("任务与拓扑图不属于同一项目", 400, "project_mismatch")
    is_primary = 1 if data.get("is_primary") else 0
    if is_primary:
        db.execute(
            "UPDATE node_task_links SET is_primary=0 WHERE diagram_id=? AND node_key=?",
            (diagram_id, node_key),
        )
    db.execute(
        """INSERT INTO node_task_links
           (diagram_id, node_key, task_id, relation, is_primary, note, created_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(diagram_id, node_key, task_id)
           DO UPDATE SET is_primary=excluded.is_primary, relation=excluded.relation""",
        (diagram_id, node_key, task_id, text(data.get("relation")) or "reference", is_primary,
         text(data.get("note")), utcnow()),
    )
    if is_primary:
        db.execute(
            "UPDATE diagram_nodes SET followup_status=? WHERE diagram_id=? AND node_key=?",
            (task["status"], diagram_id, node_key),
        )
    db.commit()
    return jsonify(_followup_node(diagram_id, node_key)), 201


@bp.delete("/<diagram_id>/nodes/<node_key>/links/<task_id>")
def remove_node_link(diagram_id, node_key, task_id):
    _get_diagram(diagram_id)
    db = get_db()
    cur = db.execute(
        "DELETE FROM node_task_links WHERE diagram_id=? AND node_key=? AND task_id=?",
        (diagram_id, node_key, task_id),
    )
    if cur.rowcount == 0:
        raise ApiError("关联不存在", 404, "link_not_found")
    remaining = db.execute(
        "SELECT t.status, l.is_primary FROM node_task_links l JOIN tasks t ON t.id=l.task_id"
        " WHERE l.diagram_id=? AND l.node_key=? ORDER BY l.is_primary DESC LIMIT 1",
        (diagram_id, node_key),
    ).fetchone()
    if remaining:
        db.execute(
            "UPDATE diagram_nodes SET followup_status=? WHERE diagram_id=? AND node_key=?",
            (remaining["status"], diagram_id, node_key),
        )
    else:
        db.execute(
            "UPDATE diagram_nodes SET followup_status='none' WHERE diagram_id=? AND node_key=?",
            (diagram_id, node_key),
        )
    db.commit()
    return jsonify(_followup_node(diagram_id, node_key))
