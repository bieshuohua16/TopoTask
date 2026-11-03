"""Project endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from db import dumps, get_db, load_json, new_id, utcnow
from services import (
    STAGES,
    STAGE_HINTS,
    STAGE_LABELS,
    STATUSES,
    STATUS_LABELS,
    clean_project_payload,
    clean_stage,
    clean_status,
    create_project_record,
    create_task_record,
    delete_project_record,
    delete_task_record,
    diagram_dict,
    ensure_project,
    project_dict,
    project_stats,
    projects_stats,
    tasks_to_dicts,
    text,
    todo_state,
    update_project_record,
    update_task_record,
)

bp = Blueprint("projects", __name__, url_prefix="/api/projects")


@bp.get("")
def list_projects():
    db = get_db()
    clauses = []
    args = []
    stage = request.args.get("stage")
    if stage and stage != "all":
        clauses.append("stage = ?")
        args.append(clean_stage(stage))
    status = request.args.get("status")
    if status and status != "all":
        clauses.append("status = ?")
        args.append(clean_status(status))
    q = text(request.args.get("q"))
    if q:
        clauses.append("(name LIKE ? OR customer LIKE ? OR code LIKE ? OR owner LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(f"SELECT * FROM projects {where} ORDER BY updated_at DESC", args).fetchall()
    items = []
    stats = projects_stats(r["id"] for r in rows)
    followups = {}
    if rows:
        placeholders = ",".join("?" * len(rows))
        nodes = db.execute(
            f"""SELECT * FROM (
                 SELECT dn.*, d.name AS diagram_name, d.project_id,
                        ROW_NUMBER() OVER (PARTITION BY d.project_id ORDER BY dn.synced_at DESC, dn.id DESC) AS position
                 FROM diagram_nodes dn JOIN diagrams d ON d.id=dn.diagram_id
                 WHERE d.project_id IN ({placeholders}) AND dn.followup_status IN ('todo','doing')
               ) WHERE position<=5 ORDER BY project_id, position""", [r["id"] for r in rows],
        )
        for node in nodes:
            item = dict(node)
            pid = item.pop("project_id")
            item.pop("position")
            followups.setdefault(pid, []).append(item)
    for row in rows:
        p = project_dict(row, stats[row["id"]])
        p["followup_nodes"] = followups.get(row["id"], [])
        items.append(p)
    return jsonify(
        {
            "items": items,
            "total": len(items),
            "stages": [{"key": k, "label": STAGE_LABELS[k], "hint": STAGE_HINTS[k]} for k in STAGES],
            "statuses": [{"key": k, "label": STATUS_LABELS[k]} for k in STATUSES],
        }
    )


def _followup_nodes(project_id: str, limit: int = 50) -> list[dict]:
    rows = get_db().execute(
        """SELECT dn.*, d.name AS diagram_name
           FROM diagram_nodes dn JOIN diagrams d ON d.id = dn.diagram_id
           WHERE d.project_id=? AND dn.followup_status IN ('todo','doing')
           ORDER BY dn.synced_at DESC LIMIT ?""",
        (project_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


@bp.post("")
def create_project():
    data = request.get_json(silent=True) or {}
    fields = clean_project_payload(data)
    pid = create_project_record(fields)
    get_db().commit()
    row = get_db().execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return jsonify(project_dict(row, project_stats(pid))), 201


@bp.get("/<project_id>")
def get_project(project_id):
    ensure_project(project_id)
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    data = project_dict(row, project_stats(project_id))
    tasks = db.execute(
        """SELECT * FROM tasks WHERE project_id=? AND status!='done'
           ORDER BY CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date, priority LIMIT 8""",
        (project_id,),
    ).fetchall()
    data["recent_tasks"] = tasks_to_dicts(tasks)
    data["diagrams"] = [
        diagram_dict(r)
        for r in db.execute(
            "SELECT * FROM diagrams WHERE project_id=? ORDER BY updated_at DESC", (project_id,)
        ).fetchall()
    ]
    data["followup_nodes"] = _followup_nodes(project_id, limit=20)
    data["activity"] = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM activity_log WHERE project_id=? ORDER BY created_at DESC LIMIT 20",
            (project_id,),
        ).fetchall()
    ]
    return jsonify(data)


@bp.patch("/<project_id>")
def patch_project(project_id):
    ensure_project(project_id)
    data = request.get_json(silent=True) or {}
    fields = clean_project_payload(data, partial=True)
    project = update_project_record(project_id, fields)
    get_db().commit()
    return jsonify(project)


@bp.delete("/<project_id>")
def delete_project(project_id):
    result = delete_project_record(project_id)
    get_db().commit()
    return jsonify(result)


# ---------------------------------------------------------------------------
# 任务台 full-state bridge
# ---------------------------------------------------------------------------
def _norm_task(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "title": t.get("title"),
        "description": t.get("description") or "",
        "priority": t.get("priority", 2),
        "status": t.get("status", "todo"),
        "stage": t.get("stage"),
        "due_date": t.get("dueDate", t.get("due_date")),
        "recur": t.get("recur"),
        "recur_day": t.get("recurDay", t.get("recur_day")),
        "category_id": t.get("projectId", t.get("category_id")),
        "tags": t.get("tags") or [],
        "subtasks": t.get("subtasks") or [],
        "sort_order": t.get("order", t.get("sort_order", 0)),
    }


@bp.get("/<project_id>/todo-state")
def get_todo_state(project_id):
    ensure_project(project_id)
    return jsonify(todo_state(project_id))


@bp.put("/<project_id>/todo-state")
def put_todo_state(project_id):
    project = ensure_project(project_id)
    data = request.get_json(silent=True) or {}
    db = get_db()
    now = utcnow()
    categories = data.get("projects") if isinstance(data.get("projects"), list) else data.get("categories")
    categories = categories if isinstance(categories, list) else []
    tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []

    # 1) 分类 upsert
    keep_categories = []
    for idx, cat in enumerate(categories):
        if not isinstance(cat, dict):
            continue
        cid = text(cat.get("id")) or new_id("c_")
        if len(cid) > 64:
            cid = new_id("c_")
        keep_categories.append(cid)
        name = text(cat.get("name")) or "未命名分类"
        color = text(cat.get("color")) or "#6366f1"
        created = text(cat.get("createdAt")) or now
        exists = db.execute("SELECT project_id FROM task_categories WHERE id=?", (cid,)).fetchone()
        if exists and exists["project_id"] != project_id:
            cid = new_id("c_")
            keep_categories[-1] = cid
            exists = None
        if exists:
            db.execute(
                "UPDATE task_categories SET name=?, color=?, sort_order=? WHERE id=? AND project_id=?",
                (name, color, idx, cid, project_id),
            )
        else:
            db.execute(
                """INSERT INTO task_categories(id, project_id, name, color, sort_order, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (cid, project_id, name, color, idx, created),
            )
    if keep_categories:
        ph = ",".join("?" * len(keep_categories))
        db.execute(
            f"DELETE FROM task_categories WHERE project_id=? AND id NOT IN ({ph})",
            [project_id, *keep_categories],
        )
    else:
        db.execute("DELETE FROM task_categories WHERE project_id=?", (project_id,))

    # 2) 任务 upsert / 显式删除
    incoming_ids = []
    for raw in tasks:
        if not isinstance(raw, dict):
            continue
        t = _norm_task(raw)
        tid = text(t.get("id"))
        existing = db.execute("SELECT project_id FROM tasks WHERE id=?", (tid,)).fetchone() if tid else None
        if existing and existing["project_id"] != project_id:
            # 不允许通过某项目的任务台状态更新去改另一个项目的任务
            t["id"] = None
            tid = create_task_record(project_id, t, source="manual", log=False)
        elif existing:
            update_task_record(tid, t, log=False)
        else:
            tid = create_task_record(project_id, t, source="manual", log=False)
        incoming_ids.append(tid)

    deleted = data.get("deleted_task_ids") or []
    for tid in deleted:
        row = db.execute(
            "SELECT id FROM tasks WHERE id=? AND project_id=?", (text(tid), project_id)
        ).fetchone()
        if row:
            delete_task_record(row["id"])

    # 3) 标签池：保留传入 + 任务实际使用，其余删除
    desired = {text(x) for x in (data.get("tags") or []) if text(x)}
    used = db.execute(
        """SELECT DISTINCT tg.name FROM task_tags tt
           JOIN tags tg ON tg.id=tt.tag_id JOIN tasks t ON t.id=tt.task_id
           WHERE t.project_id=?""",
        (project_id,),
    ).fetchall()
    desired.update(r["name"] for r in used)
    for name in desired:
        existing = db.execute(
            "SELECT id FROM tags WHERE project_id=? AND name=?", (project_id, name)
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO tags(project_id, name, created_at) VALUES (?,?,?)",
                (project_id, name, now),
            )
    existing_tags = db.execute("SELECT id, name FROM tags WHERE project_id=?", (project_id,)).fetchall()
    for tag in existing_tags:
        if tag["name"] not in desired:
            db.execute("DELETE FROM tags WHERE id=?", (tag["id"],))

    # 4) AI 配置 / 对话记录
    config = load_json(project.get("todo_config"), {})
    if "aiConfig" in data:
        config["aiConfig"] = data.get("aiConfig") or {}
    if "aiChatHistory" in data:
        config["aiChatHistory"] = data.get("aiChatHistory") or []

    db.execute(
        "UPDATE projects SET todo_config=?, updated_at=? WHERE id=?",
        (dumps(config), now, project_id),
    )
    db.commit()
    return jsonify(todo_state(project_id)), 200
