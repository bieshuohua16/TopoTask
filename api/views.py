"""Aggregated read models: dashboard, stage board, global search."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from db import get_db, utcnow
from services import (
    STAGE_HINTS,
    STAGE_LABELS,
    STAGES,
    diagram_dict,
    nodes_with_links,
    project_dict,
    project_stats,
    tasks_to_dicts,
    text,
)

bp = Blueprint("views", __name__, url_prefix="/api/views")


@bp.get("/overview")
def overview():
    db = get_db()
    projects = db.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    project_items = [project_dict(r, project_stats(r["id"])) for r in projects]
    tasks = db.execute("SELECT * FROM tasks").fetchall()
    task_count = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "done")
    overdue = sum(
        1
        for t in tasks
        if t["status"] != "done" and t["due_date"] and t["due_date"] < utcnow()
    )
    diagrams = db.execute("SELECT COUNT(*) AS n FROM diagrams").fetchone()["n"]
    followups = db.execute(
        """SELECT COUNT(*) AS n FROM diagram_nodes dn
           JOIN diagrams d ON d.id=dn.diagram_id
           WHERE d.project_id IS NOT NULL AND dn.followup_status IN ('todo','doing')"""
    ).fetchone()["n"]

    stage_stats = []
    for key in STAGES:
        stage_projects = [p for p in project_items if p["stage"] == key]
        stage_tasks = [t for t in tasks if t["stage"] == key]
        stage_stats.append(
            {
                "key": key,
                "label": STAGE_LABELS[key],
                "hint": STAGE_HINTS[key],
                "project_count": len(stage_projects),
                "task_count": len(stage_tasks),
                "open_task_count": sum(1 for t in stage_tasks if t["status"] != "done"),
                "done_task_count": sum(1 for t in stage_tasks if t["status"] == "done"),
            }
        )

    upcoming_rows = db.execute(
        """SELECT * FROM tasks WHERE status!='done' AND due_date IS NOT NULL AND due_date!=''
           ORDER BY due_date LIMIT 8"""
    ).fetchall()
    followup_rows = db.execute(
        """SELECT dn.*, d.name AS diagram_name, d.project_id, p.name AS project_name
           FROM diagram_nodes dn
           JOIN diagrams d ON d.id=dn.diagram_id
           JOIN projects p ON p.id=d.project_id
           WHERE dn.followup_status IN ('todo','doing')
           ORDER BY dn.synced_at DESC LIMIT 8"""
    ).fetchall()
    followups_out = []
    for row in followup_rows:
        item = dict(row)
        item["tasks"] = [
            dict(t)
            for t in db.execute(
                """SELECT t.id, t.title, t.status FROM node_task_links l
                   JOIN tasks t ON t.id=l.task_id
                   WHERE l.diagram_id=? AND l.node_key=? ORDER BY l.is_primary DESC""",
                (row["diagram_id"], row["node_key"]),
            ).fetchall()
        ]
        followups_out.append(item)

    return jsonify(
        {
            "project_total": len(project_items),
            "active_projects": sum(1 for p in project_items if p["status"] == "active"),
            "won_projects": sum(1 for p in project_items if p["status"] == "won"),
            "task_total": task_count,
            "task_done": done,
            "task_open": task_count - done,
            "task_overdue": overdue,
            "diagram_total": diagrams or 0,
            "followup_total": followups or 0,
            "stage_stats": stage_stats,
            "projects": project_items,
            "upcoming": tasks_to_dicts(upcoming_rows),
            "followups": followups_out,
            "stages": [{"key": k, "label": STAGE_LABELS[k], "hint": STAGE_HINTS[k]} for k in STAGES],
        }
    )


@bp.get("/stage-board")
def stage_board():
    db = get_db()
    project_id = text(request.args.get("project_id"))
    include_done = request.args.get("include_done") in ("1", "true", "yes")
    clauses = []
    args = []
    if project_id:
        clauses.append("t.project_id=?")
        args.append(project_id)
    if not include_done:
        clauses.append("t.status!='done'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(f"SELECT t.* FROM tasks t {where} ORDER BY t.priority, t.due_date", args).fetchall()
    items = tasks_to_dicts(rows)
    stages = []
    for key in STAGES:
        stage_tasks = [t for t in items if t["stage"] == key]
        project_ids = {t["project_id"] for t in stage_tasks}
        stages.append(
            {
                "key": key,
                "label": STAGE_LABELS[key],
                "hint": STAGE_HINTS[key],
                "task_count": len(stage_tasks),
                "project_count": len(project_ids),
                "tasks": stage_tasks,
            }
        )
    projects = db.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return jsonify(
        {
            "stages": stages,
            "projects": [project_dict(p, project_stats(p["id"])) for p in projects],
            "include_done": include_done,
            "project_id": project_id or None,
        }
    )


@bp.get("/links")
def links():
    """Cross-reference view: every diagram's nodes and the tasks they point at."""
    db = get_db()
    project_id = text(request.args.get("project_id"))
    clauses = []
    args = []
    if project_id:
        clauses.append("project_id=?")
        args.append(project_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    diagrams = db.execute(
        f"SELECT * FROM diagrams {where} ORDER BY updated_at DESC", args
    ).fetchall()
    items = []
    for d in diagrams:
        item = diagram_dict(d)
        item["nodes"] = nodes_with_links(d["id"])
        items.append(item)
    task_sql = """SELECT td.*, t.title, t.status, t.stage, d.name AS diagram_name,
                         d.project_id, p.name AS project_name
                  FROM task_diagrams td
                  JOIN tasks t ON t.id=td.task_id
                  JOIN diagrams d ON d.id=td.diagram_id
                  JOIN projects p ON p.id=d.project_id"""
    task_args = []
    if project_id:
        task_sql += " WHERE d.project_id=?"
        task_args.append(project_id)
    task_sql += " ORDER BY t.updated_at DESC"
    task_links = db.execute(task_sql, task_args).fetchall()
    return jsonify({"diagrams": items, "task_links": [dict(r) for r in task_links]})


@bp.get("/search")
def search():
    q = text(request.args.get("q"))
    if not q:
        return jsonify({"projects": [], "tasks": [], "diagrams": []})
    like = f"%{q}%"
    db = get_db()
    projects = db.execute(
        "SELECT * FROM projects WHERE name LIKE ? OR customer LIKE ? OR owner LIKE ? LIMIT 8",
        (like, like, like),
    ).fetchall()
    tasks = db.execute(
        "SELECT * FROM tasks WHERE title LIKE ? OR description LIKE ? LIMIT 12", (like, like)
    ).fetchall()
    diagrams = db.execute(
        "SELECT * FROM diagrams WHERE name LIKE ? OR description LIKE ? LIMIT 8", (like, like)
    ).fetchall()
    return jsonify(
        {
            "projects": [project_dict(p, project_stats(p["id"])) for p in projects],
            "tasks": tasks_to_dicts(tasks),
            "diagrams": [diagram_dict(d) for d in diagrams],
        }
    )
