"""Diagram + node endpoints."""
from __future__ import annotations

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


def _get_diagram(diagram_id: str):
    row = get_db().execute("SELECT * FROM diagrams WHERE id=?", (diagram_id,)).fetchone()
    if not row:
        raise ApiError(f"拓扑图不存在：{diagram_id}", 404, "diagram_not_found")
    return row


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
    if project_id:
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
    project_id = text(data.get("project_id"))
    if not project_id:
        raise ApiError("缺少 project_id", 400, "project_required")
    ensure_project(project_id)
    name = text(data.get("name")) or "未命名拓扑图"
    content = data.get("content")
    if not isinstance(content, dict) or "shapes" not in content:
        content = dict(EMPTY_CONTENT)
    did = new_id("d_")
    now = utcnow()
    db = get_db()
    db.execute(
        """INSERT INTO diagrams
           (id, project_id, name, kind, description, content_json, version, node_count, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            did, project_id, name, text(data.get("kind")) or "topology",
            text(data.get("description")), dumps(content), 1,
            len([s for s in (content.get("shapes") or {}).values()
                 if isinstance(s, dict) and s.get("type") == "shape"]), now, now,
        ),
    )
    sync_diagram_nodes(did, content)
    log_activity(project_id, "diagram", did, "create", name)
    db.commit()
    row = _get_diagram(did)
    return jsonify(_diagram_with_counts(row)), 201


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


@bp.patch("/<diagram_id>")
def patch_diagram(diagram_id):
    _get_diagram(diagram_id)
    data = request.get_json(silent=True) or {}
    allowed = {"name", "kind", "description"}
    fields = {k: data[k] for k in allowed if k in data}
    if not fields:
        raise ApiError("没有要更新的字段", 400, "empty_patch")
    fields = {k: text(v) for k, v in fields.items()}
    if "name" in fields and not fields["name"]:
        raise ApiError("拓扑图名称不能为空", 400, "name_required")
    fields["updated_at"] = utcnow()
    sets = ", ".join(f"{k}=?" for k in fields)
    db = get_db()
    db.execute(f"UPDATE diagrams SET {sets} WHERE id=?", [*fields.values(), diagram_id])
    db.commit()
    return jsonify(_diagram_with_counts(_get_diagram(diagram_id)))


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
