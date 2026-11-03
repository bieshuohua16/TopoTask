"""Task endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from db import ApiError, get_db, new_id, utcnow
from services import (
    clean_int,
    create_task_record,
    delete_task_record,
    ensure_project,
    task_dict,
    tasks_to_dicts,
    text,
    update_task_record,
)

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


def _filters():
    clauses = []
    args = []
    project_id = request.args.get("project_id")
    if project_id:
        clauses.append("project_id = ?")
        args.append(project_id)
    stage = request.args.get("stage")
    if stage and stage != "all":
        clauses.append("stage = ?")
        args.append(stage)
    status = request.args.get("status")
    if status and status != "all":
        clauses.append("status = ?")
        args.append(status)
    priority = request.args.get("priority")
    if priority not in (None, "", "all"):
        clauses.append("priority = ?")
        args.append(clean_int(priority, 2, 0, 3))
    q = text(request.args.get("q"))
    if q:
        clauses.append("(title LIKE ? OR description LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like])
    tag = text(request.args.get("tag"))
    if tag:
        clauses.append(
            "id IN (SELECT tt.task_id FROM task_tags tt JOIN tags tg ON tg.id=tt.tag_id WHERE tg.name=?)"
        )
        args.append(tag)
    diagram_id = text(request.args.get("diagram_id"))
    if diagram_id:
        clauses.append("id IN (SELECT task_id FROM task_diagrams WHERE diagram_id=?)")
        args.append(diagram_id)
    due = text(request.args.get("due"))
    if due == "today":
        clauses.append("due_date IS NOT NULL AND date(due_date) <= date('now','localtime')")
    elif due == "week":
        clauses.append("due_date IS NOT NULL AND date(due_date) <= date('now','localtime','+7 day')")
    elif due == "overdue":
        clauses.append("due_date IS NOT NULL AND datetime(due_date) < datetime('now') AND status!='done'")
    elif due == "none":
        clauses.append("(due_date IS NULL OR due_date='')")
    return clauses, args


@bp.get("")
def list_tasks():
    clauses, args = _filters()
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) AS n FROM tasks {where}", args).fetchone()["n"]
    limit = clean_int(request.args.get("limit"), 200, 1, 1000)
    offset = clean_int(request.args.get("offset"), 0, 0)
    order = "CASE WHEN status='done' THEN 1 ELSE 0 END, priority, due_date IS NULL, due_date"
    if request.args.get("order") == "updated":
        order = "updated_at DESC"
    rows = db.execute(
        f"SELECT * FROM tasks {where} ORDER BY {order} LIMIT ? OFFSET ?", [*args, limit, offset]
    ).fetchall()
    items = tasks_to_dicts(rows)
    return jsonify({"items": items, "total": total, "limit": limit, "offset": offset})


@bp.post("")
def create_task():
    data = request.get_json(silent=True) or {}
    project_id = text(data.get("project_id"))
    if not project_id:
        raise ApiError("缺少 project_id", 400, "project_required")
    ensure_project(project_id)
    tid = create_task_record(project_id, data, source=text(data.get("source")) or "manual")
    get_db().commit()
    return jsonify(task_dict(tid)), 201


@bp.get("/<task_id>")
def get_task(task_id):
    task = task_dict(task_id)
    if not task:
        raise ApiError(f"任务不存在：{task_id}", 404, "task_not_found")
    db = get_db()
    task["node_links"] = [
        dict(r)
        for r in db.execute(
            """SELECT l.diagram_id, l.node_key, l.is_primary, d.name AS diagram_name,
                      dn.label AS node_label
               FROM node_task_links l
               JOIN diagrams d ON d.id=l.diagram_id
               LEFT JOIN diagram_nodes dn ON dn.diagram_id=l.diagram_id AND dn.node_key=l.node_key
               WHERE l.task_id=? ORDER BY d.name""",
            (task_id,),
        ).fetchall()
    ]
    task["diagrams"] = [
        dict(r)
        for r in db.execute(
            """SELECT d.id, d.name, d.kind, td.relation FROM task_diagrams td
               JOIN diagrams d ON d.id=td.diagram_id WHERE td.task_id=? ORDER BY d.name""",
            (task_id,),
        ).fetchall()
    ]
    return jsonify(task)


@bp.patch("/<task_id>")
def patch_task(task_id):
    data = request.get_json(silent=True) or {}
    task = update_task_record(task_id, data)
    get_db().commit()
    return jsonify(task)


@bp.delete("/<task_id>")
def delete_task(task_id):
    result = delete_task_record(task_id)
    get_db().commit()
    return jsonify(result)


# ---------------------------------------------------------------------------
# Subtasks
# ---------------------------------------------------------------------------
@bp.post("/<task_id>/subtasks")
def add_subtask(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise ApiError("任务不存在", 404, "task_not_found")
    data = request.get_json(silent=True) or {}
    title = text(data.get("title"))
    if not title:
        raise ApiError("子任务标题不能为空", 400, "title_required")
    sid = new_id("st_")
    now = utcnow()
    order = db.execute("SELECT COUNT(*) AS n FROM subtasks WHERE task_id=?", (task_id,)).fetchone()["n"]
    db.execute(
        """INSERT INTO subtasks(id, task_id, title, completed, sort_order, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (sid, task_id, title, 1 if data.get("completed") else 0, order, now, now),
    )
    db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, task_id))
    db.commit()
    return jsonify({"id": sid, "title": title, "completed": bool(data.get("completed")), "sort_order": order}), 201


@bp.patch("/<task_id>/subtasks/<subtask_id>")
def patch_subtask(task_id, subtask_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM subtasks WHERE id=? AND task_id=?", (subtask_id, task_id)
    ).fetchone()
    if not row:
        raise ApiError("子任务不存在", 404, "subtask_not_found")
    data = request.get_json(silent=True) or {}
    title = text(data.get("title", row["title"])) or row["title"]
    completed = row["completed"] if "completed" not in data else (1 if data.get("completed") else 0)
    now = utcnow()
    db.execute(
        "UPDATE subtasks SET title=?, completed=?, updated_at=? WHERE id=?",
        (title, completed, now, subtask_id),
    )
    db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, task_id))
    db.commit()
    return jsonify({"id": subtask_id, "title": title, "completed": bool(completed)})


@bp.delete("/<task_id>/subtasks/<subtask_id>")
def delete_subtask(task_id, subtask_id):
    db = get_db()
    cur = db.execute("DELETE FROM subtasks WHERE id=? AND task_id=?", (subtask_id, task_id))
    if cur.rowcount == 0:
        raise ApiError("子任务不存在", 404, "subtask_not_found")
    db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (utcnow(), task_id))
    db.commit()
    return jsonify({"deleted": True, "id": subtask_id})


# ---------------------------------------------------------------------------
# Task <-> diagram
# ---------------------------------------------------------------------------
@bp.post("/<task_id>/diagrams")
def link_diagram(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise ApiError("任务不存在", 404, "task_not_found")
    data = request.get_json(silent=True) or {}
    diagram_id = text(data.get("diagram_id"))
    diagram = db.execute(
        "SELECT * FROM diagrams WHERE id=? AND project_id=?", (diagram_id, task["project_id"])
    ).fetchone()
    if not diagram:
        raise ApiError("拓扑图不存在或不属于该项目", 404, "diagram_not_found")
    db.execute(
        """INSERT INTO task_diagrams(task_id, diagram_id, relation, note, created_at)
           VALUES (?,?,?,?,?) ON CONFLICT(task_id, diagram_id) DO UPDATE SET relation=excluded.relation""",
        (task_id, diagram_id, text(data.get("relation")) or "related", text(data.get("note")), utcnow()),
    )
    db.commit()
    return jsonify({"task_id": task_id, "diagram_id": diagram_id, "diagram_name": diagram["name"]}), 201


@bp.delete("/<task_id>/diagrams/<diagram_id>")
def unlink_diagram(task_id, diagram_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM task_diagrams WHERE task_id=? AND diagram_id=?", (task_id, diagram_id)
    )
    if cur.rowcount == 0:
        raise ApiError("关联不存在", 404, "link_not_found")
    db.commit()
    return jsonify({"deleted": True, "task_id": task_id, "diagram_id": diagram_id})


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------
@bp.put("/<task_id>/tags")
def set_tags(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise ApiError("任务不存在", 404, "task_not_found")
    data = request.get_json(silent=True) or {}
    from services import _set_task_tags

    _set_task_tags(task_id, task["project_id"], data.get("tags") or [])
    db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (utcnow(), task_id))
    db.commit()
    return jsonify(task_dict(task_id))
