"""Domain helpers shared by the API blueprints."""
from __future__ import annotations

from typing import Iterable

from db import ApiError, get_db, load_json, new_id, utcnow

STAGES = ("research", "proposal", "poc", "bidding")
STAGE_LABELS = {
    "research": "需求调研",
    "proposal": "方案编写",
    "poc": "POC 验证",
    "bidding": "招投标",
}
STAGE_HINTS = {
    "research": "客户访谈、现状梳理、需求边界",
    "proposal": "方案设计、配置报价、技术交流",
    "poc": "环境部署、测试验证、问题闭环",
    "bidding": "标书应答、资质材料、投标节点",
}
STATUSES = ("active", "won", "lost", "paused")
STATUS_LABELS = {"active": "跟进中", "won": "已赢单", "lost": "已丢单", "paused": "已暂停"}
TASK_STATUSES = ("todo", "doing", "done")
TASK_STATUS_LABELS = {"todo": "待办", "doing": "进行中", "done": "已完成"}
PRIORITY_LABELS = {0: "P0 紧急", 1: "P1 重要", 2: "P2 一般", 3: "P3 低"}


def clean_stage(value: str | None, fallback: str = "research") -> str:
    return value if value in STAGES else fallback


def clean_status(value: str | None, fallback: str = "active") -> str:
    return value if value in STATUSES else fallback


def clean_task_status(value: str | None, fallback: str = "todo") -> str:
    return value if value in TASK_STATUSES else fallback


def clean_int(value, fallback=0, lo=None, hi=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def text(value, default="") -> str:
    if value is None:
        return default
    return str(value).strip()


def ensure_project(project_id: str) -> dict:
    row = get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise ApiError(f"项目不存在：{project_id}", 404, "project_not_found")
    return dict(row)


def log_activity(project_id: str, entity_type: str, entity_id: str | None, action: str, detail: str = ""):
    get_db().execute(
        "INSERT INTO activity_log(project_id, entity_type, entity_id, action, detail, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, entity_type, entity_id, action, detail, utcnow()),
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
def project_dict(row, stats: dict | None = None) -> dict:
    data = dict(row)
    # 旧任务台的 todo_config（含历史 AI Key）只保留在数据库和服务端 todo-state 接口，
    # 不再随项目对象返回给页面 / 浏览器。
    data.pop("todo_config", None)
    data["metadata"] = load_json(data.get("metadata"), {})
    data["stage_label"] = STAGE_LABELS.get(data["stage"], data["stage"])
    data["status_label"] = STATUS_LABELS.get(data["status"], data["status"])
    if stats is not None:
        data.update(stats)
    return data


def project_stats(project_id: str) -> dict:
    db = get_db()
    counts = db.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done,
             SUM(CASE WHEN status='doing' THEN 1 ELSE 0 END) AS doing,
             SUM(CASE WHEN status!='done' THEN 1 ELSE 0 END) AS open
           FROM tasks WHERE project_id=?""",
        (project_id,),
    ).fetchone()
    diagram = db.execute(
        "SELECT COUNT(*) AS n FROM diagrams WHERE project_id=?", (project_id,)
    ).fetchone()
    followup = db.execute(
        """SELECT COUNT(*) AS n FROM diagram_nodes dn
           JOIN diagrams d ON d.id = dn.diagram_id
           WHERE d.project_id=? AND dn.followup_status IN ('todo','doing')""",
        (project_id,),
    ).fetchone()
    next_due = db.execute(
        """SELECT due_date FROM tasks
           WHERE project_id=? AND status!='done' AND due_date IS NOT NULL AND due_date!=''
           ORDER BY due_date ASC LIMIT 1""",
        (project_id,),
    ).fetchone()
    total = counts["total"] or 0
    done = counts["done"] or 0
    return {
        "task_total": total,
        "task_done": done,
        "task_doing": counts["doing"] or 0,
        "task_open": counts["open"] or 0,
        "task_progress": round(done / total * 100) if total else 0,
        "diagram_count": diagram["n"] or 0,
        "followup_count": followup["n"] or 0,
        "next_due": next_due["due_date"] if next_due else None,
    }


PROJECT_FIELDS = (
    "name", "code", "customer", "industry", "owner", "stage", "status",
    "description", "color", "start_date", "end_date",
)


def clean_project_payload(data: dict, partial: bool = False) -> dict:
    """Normalise project fields from a form or an AI draft."""
    out = {}
    for key in PROJECT_FIELDS:
        if key in data:
            out[key] = data[key]
    if "name" in out:
        out["name"] = text(out["name"])
    for key in ("code", "customer", "industry", "owner", "description"):
        if key in out:
            out[key] = text(out[key])
    if "stage" in out:
        out["stage"] = clean_stage(out["stage"])
    if "status" in out:
        out["status"] = clean_status(out["status"])
    if not partial and not out.get("name"):
        raise ApiError("项目名称不能为空", 400, "name_required")
    return out


def create_project_record(fields: dict) -> str:
    """Insert a project plus its default task category. Caller commits."""
    db = get_db()
    pid = new_id("p_")
    now = utcnow()
    fields = dict(fields)
    fields.setdefault("name", "")
    fields["color"] = fields.get("color") or "#5b6cf0"
    fields["stage"] = clean_stage(fields.get("stage"), "research")
    fields["status"] = clean_status(fields.get("status"), "active")
    fields["description"] = fields.get("description") or ""
    db.execute(
        """INSERT INTO projects
           (id, name, code, customer, industry, owner, stage, status, description, color,
            start_date, end_date, todo_config, metadata, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, '{}', '{}', ?, ?)""",
        (
            pid, fields["name"], fields.get("code"), fields.get("customer"),
            fields.get("industry"), fields.get("owner"), fields["stage"], fields["status"],
            fields["description"], fields["color"], fields.get("start_date"),
            fields.get("end_date"), now, now,
        ),
    )
    # 每个项目默认带一个任务分类，任务台的「项目」下拉才有可选项
    db.execute(
        "INSERT INTO task_categories(id, project_id, name, color, sort_order, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (new_id("c_"), pid, "默认分类", "#6366f1", 0, now),
    )
    log_activity(pid, "project", pid, "create", fields["name"])
    return pid


def update_project_record(project_id: str, fields: dict) -> dict:
    """Update project fields, log the change and return the fresh project dict. Caller commits."""
    ensure_project(project_id)
    fields = dict(fields)
    fields.pop("id", None)
    if not fields:
        raise ApiError("没有要更新的字段", 400, "empty_patch")
    db = get_db()
    fields["updated_at"] = utcnow()
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE projects SET {sets} WHERE id=?", [*fields.values(), project_id])
    log_activity(
        project_id, "project", project_id, "update",
        ", ".join(k for k in fields if k != "updated_at"),
    )
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return project_dict(row, project_stats(project_id))


def delete_project_record(project_id: str) -> dict:
    """Delete a project (tasks/diagrams cascade). Caller commits."""
    project = ensure_project(project_id)
    get_db().execute("DELETE FROM projects WHERE id=?", (project_id,))
    return {"deleted": True, "id": project_id, "name": project["name"]}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
def _tags_for_tasks(task_ids: Iterable[str]) -> dict[str, list[str]]:
    ids = list(task_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = get_db().execute(
        f"""SELECT tt.task_id, t.name FROM task_tags tt
            JOIN tags t ON t.id = tt.tag_id
            WHERE tt.task_id IN ({placeholders}) ORDER BY t.name""",
        ids,
    ).fetchall()
    out: dict[str, list[str]] = {i: [] for i in ids}
    for r in rows:
        out.setdefault(r["task_id"], []).append(r["name"])
    return out


def _subtasks_for_tasks(task_ids: Iterable[str]) -> dict[str, list[dict]]:
    ids = list(task_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = get_db().execute(
        f"""SELECT * FROM subtasks WHERE task_id IN ({placeholders})
            ORDER BY sort_order, created_at""",
        ids,
    ).fetchall()
    out: dict[str, list[dict]] = {i: [] for i in ids}
    for r in rows:
        out.setdefault(r["task_id"], []).append(
            {
                "id": r["id"],
                "title": r["title"],
                "completed": bool(r["completed"]),
                "sort_order": r["sort_order"],
            }
        )
    return out


def _diagrams_for_tasks(task_ids: Iterable[str]) -> dict[str, list[dict]]:
    ids = list(task_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = get_db().execute(
        f"""SELECT td.task_id, d.id, d.name, d.kind, td.relation
            FROM task_diagrams td JOIN diagrams d ON d.id = td.diagram_id
            WHERE td.task_id IN ({placeholders}) ORDER BY d.name""",
        ids,
    ).fetchall()
    out: dict[str, list[dict]] = {i: [] for i in ids}
    for r in rows:
        out.setdefault(r["task_id"], []).append(
            {"id": r["id"], "name": r["name"], "kind": r["kind"], "relation": r["relation"]}
        )
    return out


def tasks_to_dicts(rows, with_details: bool = True) -> list[dict]:
    rows = list(rows)
    ids = [r["id"] for r in rows]
    tags = _tags_for_tasks(ids) if with_details else {}
    subs = _subtasks_for_tasks(ids) if with_details else {}
    diagrams = _diagrams_for_tasks(ids) if with_details else {}
    project_names = {}
    if rows:
        pids = {r["project_id"] for r in rows}
        ph = ",".join("?" * len(pids))
        for p in get_db().execute(f"SELECT id, name FROM projects WHERE id IN ({ph})", list(pids)):
            project_names[p["id"]] = p["name"]
    out = []
    for r in rows:
        d = dict(r)
        d["priority_label"] = PRIORITY_LABELS.get(d["priority"], "")
        d["stage_label"] = STAGE_LABELS.get(d["stage"], d["stage"])
        d["status_label"] = TASK_STATUS_LABELS.get(d["status"], d["status"])
        d["project_name"] = project_names.get(d["project_id"], "")
        d["tags"] = tags.get(d["id"], [])
        d["subtasks"] = subs.get(d["id"], [])
        d["diagrams"] = diagrams.get(d["id"], [])
        d["subtask_total"] = len(d["subtasks"])
        d["subtask_done"] = sum(1 for s in d["subtasks"] if s["completed"])
        out.append(d)
    return out


def task_dict(task_id: str) -> dict | None:
    row = get_db().execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return None
    return tasks_to_dicts([row])[0]


def _set_task_tags(task_id: str, project_id: str, names: list[str], db=None) -> None:
    db = db or get_db()
    db.execute("DELETE FROM task_tags WHERE task_id=?", (task_id,))
    seen = set()
    for raw in names or []:
        name = text(raw)
        if not name or name in seen:
            continue
        seen.add(name)
        row = db.execute(
            "SELECT id FROM tags WHERE project_id=? AND name=?", (project_id, name)
        ).fetchone()
        if row:
            tag_id = row["id"]
        else:
            cur = db.execute(
                "INSERT INTO tags(project_id, name, created_at) VALUES (?,?,?)",
                (project_id, name, utcnow()),
            )
            tag_id = cur.lastrowid
        db.execute(
            "INSERT OR IGNORE INTO task_tags(task_id, tag_id) VALUES (?,?)", (task_id, tag_id)
        )


def _replace_subtasks(task_id: str, subtasks: list[dict], db=None) -> None:
    db = db or get_db()
    keep = []
    now = utcnow()
    for idx, sub in enumerate(subtasks or []):
        if not isinstance(sub, dict):
            continue
        sid = text(sub.get("id")) or new_id("st_")
        if len(sid) > 64:
            sid = new_id("st_")
        keep.append(sid)
        title = text(sub.get("title"))
        if not title:
            continue
        done = 1 if sub.get("completed") else 0
        old = db.execute("SELECT id, task_id FROM subtasks WHERE id=?", (sid,)).fetchone()
        if old and old["task_id"] != task_id:
            sid = new_id("st_")
            old = None
            keep[-1] = sid
        if old:
            db.execute(
                "UPDATE subtasks SET title=?, completed=?, sort_order=?, updated_at=? WHERE id=?",
                (title, done, idx, now, sid),
            )
        else:
            db.execute(
                """INSERT INTO subtasks(id, task_id, title, completed, sort_order, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (sid, task_id, title, done, idx, now, now),
            )
    if keep:
        ph = ",".join("?" * len(keep))
        db.execute(f"DELETE FROM subtasks WHERE task_id=? AND id NOT IN ({ph})", [task_id, *keep])
    else:
        db.execute("DELETE FROM subtasks WHERE task_id=?", (task_id,))


def create_task_record(project_id: str, payload: dict, source: str = "manual", log: bool = True) -> str:
    db = get_db()
    project = ensure_project(project_id)
    now = utcnow()
    task_id = text(payload.get("id")) or new_id("t_")
    if len(task_id) > 64:
        task_id = new_id("t_")
    exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
    if exists:
        task_id = new_id("t_")
    title = text(payload.get("title")) or "未命名任务"
    status = clean_task_status(payload.get("status"), "todo")
    stage = clean_stage(payload.get("stage"), project["stage"])
    category_id = text(payload.get("category_id")) or None
    if category_id:
        cat = db.execute(
            "SELECT 1 FROM task_categories WHERE id=? AND project_id=?", (category_id, project_id)
        ).fetchone()
        category_id = category_id if cat else None
    if not category_id:
        # 归入项目的第一个分类，保证任务台的「项目」筛选下能看到
        first_cat = db.execute(
            "SELECT id FROM task_categories WHERE project_id=? ORDER BY sort_order, created_at LIMIT 1",
            (project_id,),
        ).fetchone()
        category_id = first_cat["id"] if first_cat else None
    priority = clean_int(payload.get("priority"), 2, 0, 3)
    if "sort_order" in payload and payload.get("sort_order") is not None:
        try:
            sort_order = float(payload.get("sort_order"))
        except (TypeError, ValueError):
            sort_order = 0.0
    else:
        row = db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM tasks WHERE project_id=?",
            (project_id,),
        ).fetchone()
        sort_order = float(row["n"])
    db.execute(
        """INSERT INTO tasks
           (id, project_id, category_id, title, description, priority, status, stage, due_date,
            recur, recur_day, sort_order, source, completed_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id, project_id, category_id, title, text(payload.get("description")), priority,
            status, stage, payload.get("due_date") or None, payload.get("recur") or None,
            payload.get("recur_day"), sort_order, source,
            now if status == "done" else None, now, now,
        ),
    )
    _set_task_tags(task_id, project_id, payload.get("tags") or [], db)
    _replace_subtasks(task_id, payload.get("subtasks") or [], db)
    if log:
        log_activity(project_id, "task", task_id, "create", title)
    return task_id


def update_task_record(task_id: str, payload: dict, log: bool = True) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise ApiError(f"任务不存在：{task_id}", 404, "task_not_found")
    task = dict(row)
    project = ensure_project(task["project_id"])
    fields = {
        "title": text(payload.get("title")) or task["title"],
        "description": text(payload.get("description")) if "description" in payload else task["description"],
        "priority": clean_int(payload.get("priority"), task["priority"], 0, 3),
        "status": clean_task_status(payload.get("status"), task["status"]),
        "stage": clean_stage(payload.get("stage"), task["stage"]),
        "due_date": payload.get("due_date", task["due_date"]) or None,
        "recur": payload.get("recur", task["recur"]) or None,
        "recur_day": payload.get("recur_day", task["recur_day"]),
        "category_id": payload.get("category_id", task["category_id"]),
        "sort_order": payload.get("sort_order", task["sort_order"]),
    }
    try:
        fields["sort_order"] = float(fields["sort_order"])
    except (TypeError, ValueError):
        fields["sort_order"] = task["sort_order"]
    if fields["category_id"]:
        cat = db.execute(
            "SELECT 1 FROM task_categories WHERE id=? AND project_id=?",
            (fields["category_id"], task["project_id"]),
        ).fetchone()
        if not cat:
            fields["category_id"] = None
    completed_at = task["completed_at"]
    status_changed = fields["status"] != task["status"]
    if fields["status"] == "done" and task["status"] != "done":
        completed_at = utcnow()
    elif fields["status"] != "done":
        completed_at = None
    db.execute(
        """UPDATE tasks SET title=?, description=?, priority=?, status=?, stage=?, due_date=?,
           recur=?, recur_day=?, category_id=?, sort_order=?, completed_at=?, updated_at=?
           WHERE id=?""",
        (
            fields["title"], fields["description"], fields["priority"], fields["status"],
            fields["stage"], fields["due_date"], fields["recur"], fields["recur_day"],
            fields["category_id"], fields["sort_order"], completed_at, utcnow(), task_id,
        ),
    )
    if "tags" in payload:
        _set_task_tags(task_id, task["project_id"], payload.get("tags") or [], db)
    if "subtasks" in payload:
        _replace_subtasks(task_id, payload.get("subtasks") or [], db)
    if status_changed:
        sync_node_status_for_task(task_id)
    if log:
        log_activity(task["project_id"], "task", task_id, "update", fields["title"])
    return task_dict(task_id)


def delete_task_record(task_id: str) -> dict:
    """Delete a task and clear the follow-up badge of nodes left without tasks. Caller commits."""
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise ApiError(f"任务不存在：{task_id}", 404, "task_not_found")
    diagrams = db.execute(
        "SELECT DISTINCT diagram_id, node_key FROM node_task_links WHERE task_id=?", (task_id,)
    ).fetchall()
    db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    for link in diagrams:
        remaining = db.execute(
            "SELECT 1 FROM node_task_links WHERE diagram_id=? AND node_key=? LIMIT 1",
            (link["diagram_id"], link["node_key"]),
        ).fetchone()
        if not remaining:
            db.execute(
                "UPDATE diagram_nodes SET followup_status='none' WHERE diagram_id=? AND node_key=?",
                (link["diagram_id"], link["node_key"]),
            )
    log_activity(row["project_id"], "task", task_id, "delete", row["title"])
    return {"deleted": True, "id": task_id, "title": row["title"], "project_id": row["project_id"]}


def sync_node_status_for_task(task_id: str) -> None:
    """Keep the node follow-up badge in step with its primary task status."""
    db = get_db()
    row = db.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return
    db.execute(
        """UPDATE diagram_nodes SET followup_status = ?
           WHERE (diagram_id, node_key) IN (
             SELECT diagram_id, node_key FROM node_task_links
             WHERE task_id=? AND is_primary=1
           ) AND followup_status != 'none'""",
        (row["status"], task_id),
    )


# ---------------------------------------------------------------------------
# Diagrams / nodes
# ---------------------------------------------------------------------------
def extract_nodes(content: dict) -> list[dict]:
    """Read canvas shapes into an indexable node list (connectors excluded)."""
    shapes = content.get("shapes") or {}
    order = content.get("order") or list(shapes.keys())
    nodes = []
    for key in order:
        shape = shapes.get(key)
        if not isinstance(shape, dict) or shape.get("type") != "shape":
            continue
        label = (shape.get("text") or "").split("\n")[0].strip() or "未命名节点"
        nodes.append(
            {
                "node_key": str(shape.get("id") or key),
                "label": label[:200],
                "kind": shape.get("kind") or "rect",
                "x": shape.get("x"),
                "y": shape.get("y"),
                "w": shape.get("w"),
                "h": shape.get("h"),
            }
        )
    return nodes


def sync_diagram_nodes(diagram_id: str, content: dict) -> int:
    """Upsert parsed nodes, preserve follow-up status, drop removed nodes."""
    db = get_db()
    current = {
        r["node_key"]: r
        for r in db.execute("SELECT * FROM diagram_nodes WHERE diagram_id=?", (diagram_id,))
    }
    nodes = extract_nodes(content)
    keep = set()
    now = utcnow()
    for node in nodes:
        keep.add(node["node_key"])
        old = current.get(node["node_key"])
        if old:
            db.execute(
                """UPDATE diagram_nodes SET label=?, kind=?, x=?, y=?, w=?, h=?, synced_at=?
                   WHERE diagram_id=? AND node_key=?""",
                (node["label"], node["kind"], node["x"], node["y"], node["w"], node["h"], now,
                 diagram_id, node["node_key"]),
            )
        else:
            db.execute(
                """INSERT INTO diagram_nodes
                   (diagram_id, node_key, label, kind, x, y, w, h, followup_status, note, synced_at)
                   VALUES (?,?,?,?,?,?,?,?, 'none', '', ?)""",
                (diagram_id, node["node_key"], node["label"], node["kind"], node["x"], node["y"],
                 node["w"], node["h"], now),
            )
    for key in set(current) - keep:
        db.execute(
            "DELETE FROM node_task_links WHERE diagram_id=? AND node_key=?", (diagram_id, key)
        )
        db.execute(
            "DELETE FROM diagram_nodes WHERE diagram_id=? AND node_key=?", (diagram_id, key)
        )
    return len(nodes)


def node_dict(row) -> dict:
    d = dict(row)
    d["linked_tasks"] = []
    d["primary_task"] = None
    return d


def nodes_with_links(diagram_id: str) -> list[dict]:
    db = get_db()
    nodes = db.execute(
        "SELECT * FROM diagram_nodes WHERE diagram_id=? ORDER BY label", (diagram_id,)
    ).fetchall()
    links = db.execute(
        """SELECT l.*, t.title, t.status, t.priority, t.due_date
           FROM node_task_links l JOIN tasks t ON t.id = l.task_id
           WHERE l.diagram_id=? ORDER BY l.is_primary DESC, t.created_at""",
        (diagram_id,),
    ).fetchall()
    by_node: dict[str, list[dict]] = {}
    for link in links:
        by_node.setdefault(link["node_key"], []).append(dict(link))
    out = []
    for row in nodes:
        d = node_dict(row)
        d["linked_tasks"] = by_node.get(row["node_key"], [])
        primary = next((t for t in d["linked_tasks"] if t["is_primary"]), None)
        d["primary_task"] = primary
        out.append(d)
    return out


def diagram_dict(row, include_nodes: bool = False) -> dict:
    d = dict(row)
    d.pop("content_json", None)
    if include_nodes:
        d["nodes"] = nodes_with_links(d["id"])
    return d


def merge_followup_into_content(diagram_id: str, content: dict) -> dict:
    """Attach node follow-up metadata so the canvas can render badges."""
    nodes = {n["node_key"]: n for n in nodes_with_links(diagram_id)}
    shapes = content.get("shapes") or {}
    for key, shape in shapes.items():
        if not isinstance(shape, dict) or shape.get("type") != "shape":
            continue
        node = nodes.get(str(shape.get("id") or key))
        if not node:
            continue
        shape["tt"] = {
            "status": node["followup_status"],
            "label": node["label"],
            "nodeKey": node["node_key"],
            "tasks": [
                {
                    "id": t["task_id"],
                    "title": t["title"],
                    "status": t["status"],
                    "primary": bool(t["is_primary"]),
                }
                for t in node["linked_tasks"]
            ],
        }
    return content


def content_of(row) -> dict:
    return load_json(row["content_json"], {"app": "topotash", "version": 2, "shapes": {}, "order": [], "groups": {}, "imagePool": {}})


# ---------------------------------------------------------------------------
# 任务台 bridge
# ---------------------------------------------------------------------------
def todo_state(project_id: str) -> dict:
    db = get_db()
    project = ensure_project(project_id)
    categories = db.execute(
        "SELECT * FROM task_categories WHERE project_id=? ORDER BY sort_order, name",
        (project_id,),
    ).fetchall()
    tasks = db.execute(
        "SELECT * FROM tasks WHERE project_id=? ORDER BY sort_order, created_at",
        (project_id,),
    ).fetchall()
    tag_rows = db.execute("SELECT name FROM tags WHERE project_id=? ORDER BY name", (project_id,)).fetchall()
    detailed = tasks_to_dicts(tasks)
    config = load_json(project.get("todo_config"), {})
    out_tasks = []
    for t in detailed:
        out_tasks.append(
            {
                "id": t["id"],
                "title": t["title"],
                "description": t["description"],
                "priority": t["priority"],
                "status": t["status"],
                "stage": t["stage"],
                "dueDate": t["due_date"],
                "recur": t["recur"],
                "recurDay": t["recur_day"],
                "projectId": t["category_id"],
                "source": t["source"],
                "tags": t["tags"],
                "subtasks": [
                    {"id": s["id"], "title": s["title"], "completed": s["completed"]}
                    for s in t["subtasks"]
                ],
                "order": t["sort_order"],
                "createdAt": t["created_at"],
                "updatedAt": t["updated_at"],
            }
        )
    return {
        "version": "2.0",
        "lastModified": project["updated_at"],
        "projects": [
            {
                "id": c["id"],
                "name": c["name"],
                "color": c["color"],
                "createdAt": c["created_at"],
            }
            for c in categories
        ],
        "tags": [r["name"] for r in tag_rows],
        "tasks": out_tasks,
        "aiConfig": config.get("aiConfig", {}),
        "aiChatHistory": config.get("aiChatHistory", []),
        "topotash": {
            "projectId": project["id"],
            "projectName": project["name"],
            "stage": project["stage"],
            "stageLabel": STAGE_LABELS.get(project["stage"], project["stage"]),
        },
    }
