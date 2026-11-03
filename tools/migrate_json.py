"""Import historical task JSON and canvas JSON into TopoTash SQLite.

Examples
--------
# 1) 把任务 JSON 导入成一个项目（原有「项目分类」变成任务分类）
python tools/migrate_json.py --todo data/todos.json --project-name "历史任务迁移"

# 2) 每个旧「项目分类」拆成一个 TopoTash 项目
python tools/migrate_json.py --todo data/todos.json --split-projects

# 3) 同时导入目录下所有画布 JSON（挂到第一个项目）
python tools/migrate_json.py --todo data/todos.json --visio data/diagrams

# 4) 指定目标数据库 / 目标项目 / 阶段
python tools/migrate_json.py --todo todos.json --db my.db --project-name "XX 银行" --stage poc
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from db import dumps, get_db, init_db, new_id, utcnow  # noqa: E402
from services import STAGES, sync_diagram_nodes  # noqa: E402

COLORS = ["#5b6cf0", "#0d9488", "#d97706", "#dc2626", "#7c3aed", "#2563eb", "#db2777"]


def _parse_args():
    p = argparse.ArgumentParser(description="Migration: historical task JSON / canvas JSON -> TopoTash SQLite")
    p.add_argument("--todo", help="任务 JSON 文件（version 2.0）")
    p.add_argument("--visio", action="append", default=[], help="画布 JSON 文件或目录（可重复）")
    p.add_argument("--project-name", default="", help="导入任务数据时创建的 TopoTash 项目名")
    p.add_argument("--split-projects", action="store_true", help="每个旧分类创建一个 TopoTash 项目")
    p.add_argument("--stage", default="research", choices=list(STAGES), help="Default pre-sales stage")
    p.add_argument("--visio-project", default="", help="Existing project name/id to attach diagrams to")
    p.add_argument("--db", default=str(ROOT / "topotash.db"), help="SQLite database path")
    p.add_argument("--dry-run", action="store_true", help="Parse and report, write nothing")
    return p.parse_args()


def _create_project(db, name, stage, color, description="", todo_config=None):
    pid = new_id("p_")
    now = utcnow()
    db.execute(
        """INSERT INTO projects
           (id, name, code, customer, industry, owner, stage, status, description, color,
            start_date, end_date, todo_config, metadata, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, name, "", "", "", "", stage, "active", description, color, None, None,
         dumps(todo_config or {}), "{}", now, now),
    )
    return pid


def _create_category(db, project_id, name, color, order):
    cid = new_id("c_")
    db.execute(
        "INSERT INTO task_categories(id, project_id, name, color, sort_order, created_at) VALUES (?,?,?,?,?,?)",
        (cid, project_id, name, color, order, utcnow()),
    )
    return cid


def _ensure_tag(db, project_id, name, cache):
    key = (project_id, name)
    if key in cache:
        return cache[key]
    row = db.execute(
        "SELECT id FROM tags WHERE project_id=? AND name=?", (project_id, name)
    ).fetchone()
    if row:
        cache[key] = row["id"]
    else:
        cur = db.execute(
            "INSERT INTO tags(project_id, name, color, created_at) VALUES (?,?,?,?)",
            (project_id, name, "#64748b", utcnow()),
        )
        cache[key] = cur.lastrowid
    return cache[key]


def _insert_task(db, project_id, category_id, t, index, stage, tag_cache):
    task_id = str(t.get("id") or new_id("t_"))
    if db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
        task_id = new_id("t_")
    status = t.get("status") if t.get("status") in ("todo", "doing", "done") else "todo"
    due = t.get("dueDate") or t.get("due_date")
    created_at = t.get("createdAt") or utcnow()
    updated_at = t.get("updatedAt") or created_at
    # ``0`` is a valid priority (P0) and a valid sort order, so it must not be
    # swallowed by an ``or`` fallback.
    raw_priority = t.get("priority")
    try:
        priority = 2 if raw_priority in (None, "") else max(0, min(3, int(raw_priority)))
    except (TypeError, ValueError):
        priority = 2
    order = t.get("order")
    order = index if order is None else order
    db.execute(
        """INSERT INTO tasks
           (id, project_id, category_id, title, description, priority, status, stage, due_date,
            recur, recur_day, sort_order, source, completed_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'import', ?, ?, ?)""",
        (
            task_id, project_id, category_id, str(t.get("title") or "未命名任务")[:500],
            str(t.get("description") or ""), priority,
            status, t.get("stage") if t.get("stage") in STAGES else stage, due,
            t.get("recur"), t.get("recurDay"), order,
            utcnow() if status == "done" else None, created_at, updated_at,
        ),
    )
    for si, sub in enumerate(t.get("subtasks") or []):
        sid = str(sub.get("id") or new_id("st_"))
        if db.execute("SELECT 1 FROM subtasks WHERE id=?", (sid,)).fetchone():
            sid = new_id("st_")
        db.execute(
            """INSERT INTO subtasks(id, task_id, title, completed, sort_order, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, task_id, str(sub.get("title") or "")[:500], 1 if sub.get("completed") else 0,
             si, created_at, updated_at),
        )
    for raw_tag in t.get("tags") or []:
        tag = str(raw_tag).strip()
        if not tag:
            continue
        tag_id = _ensure_tag(db, project_id, tag, tag_cache)
        db.execute("INSERT OR IGNORE INTO task_tags(task_id, tag_id) VALUES (?,?)", (task_id, tag_id))
    return task_id


def _import_todo(db, data, project_name, split_projects, stage, dry_run, tag_pool):
    tasks = data.get("tasks") or []
    old_projects = data.get("projects") or []
    config = {
        "aiConfig": data.get("aiConfig") or {},
        "aiChatHistory": data.get("aiChatHistory") or [],
    }
    created = []
    tag_cache = {}
    inserted = 0

    if dry_run:
        if split_projects:
            names = {str(p.get("name") or "未命名分类") for p in old_projects}
            names.add("未分类任务")
            return [(f"dry_{i}", n) for i, n in enumerate(names)], len(tasks), len(tag_pool)
        return [("dry", project_name or "历史任务迁移")], len(tasks), len(tag_pool)

    if split_projects:
        groups: dict[str, list] = {}
        for old in old_projects:
            groups[str(old.get("id"))] = []
        for t in tasks:
            groups.setdefault(str(t.get("projectId") or "__none__"), []).append(t)
        old_by_id = {str(p.get("id")): p for p in old_projects}
        for i, (old_id, items) in enumerate(groups.items()):
            old = old_by_id.get(old_id) or {}
            name = str(old.get("name") or "未分类任务")
            pid = _create_project(
                db, name, stage, old.get("color") or COLORS[i % len(COLORS)],
                f"由历史任务分类「{name}」迁移", config if i == 0 else {},
            )
            cid = _create_category(db, pid, "默认分类", "#6366f1", 0)
            for idx, t in enumerate(items):
                _insert_task(db, pid, cid, t, idx, stage, tag_cache)
                inserted += 1
            created.append((pid, name))
    else:
        name = project_name or "历史任务迁移"
        pid = _create_project(db, name, stage, COLORS[0], "由历史任务 JSON 迁移", config)
        cat_map = {}
        for i, old in enumerate(old_projects):
            cat_map[str(old.get("id"))] = _create_category(
                db, pid, str(old.get("name") or "未命名分类"),
                old.get("color") or COLORS[i % len(COLORS)], i,
            )
        default_cid = next(iter(cat_map.values()), None)
        if not default_cid:
            default_cid = _create_category(db, pid, "默认分类", "#6366f1", 0)
        for idx, t in enumerate(tasks):
            cid = cat_map.get(str(t.get("projectId"))) or default_cid
            _insert_task(db, pid, cid, t, idx, stage, tag_cache)
            inserted += 1
        created.append((pid, name))

    # 保留标签池（即使某个标签暂时没挂在任务上）
    for pid, _name in created:
        for tag in tag_pool:
            _ensure_tag(db, pid, tag, tag_cache)
    return created, inserted, len(tag_pool)


def _visio_files(paths):
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.vweb.json")))
            for f in sorted(p.rglob("*.json")):
                if f.name.endswith(".vweb.json"):
                    continue
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(d, dict) and isinstance(d.get("shapes"), dict):
                    files.append(f)
        elif p.is_file():
            files.append(p)
    seen, out = set(), []
    for f in files:
        key = str(f.resolve())
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _import_visio(db, files, target_project_id, dry_run):
    imported = 0
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ! 跳过 {file}: {exc}")
            continue
        if not isinstance(data, dict) or not isinstance(data.get("shapes"), dict):
            continue
        name = file.name
        for suffix in (".vweb.json", ".json"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        name = name.replace("_", " ").strip() or "导入的拓扑图"
        if dry_run:
            imported += 1
            continue
        if db.execute("SELECT 1 FROM diagrams WHERE project_id=? AND name=?", (target_project_id, name)).fetchone():
            name = f"{name} (导入)"
        did = new_id("d_")
        now = utcnow()
        node_count = len([s for s in data["shapes"].values()
                          if isinstance(s, dict) and s.get("type") == "shape"])
        db.execute(
            """INSERT INTO diagrams
               (id, project_id, name, kind, description, content_json, version, node_count, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (did, target_project_id, name[:200], "topology", f"从 {file.name} 导入",
             dumps(data), int(data.get("version") or 2), node_count, now, now),
        )
        sync_diagram_nodes(did, data)
        imported += 1
    return imported


def main():
    args = _parse_args()
    if not args.todo and not args.visio:
        print("请至少提供 --todo 或 --visio")
        return 2

    app = create_app({"DATABASE": args.db})
    with app.app_context():
        db = get_db()
        init_db(app)
        created = []
        if args.todo:
            path = Path(args.todo)
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data.get("tasks"), list):
                print("任务 JSON 格式不正确：缺少 tasks 数组")
                return 1
            print(f"读取任务 JSON: {path} · {len(data.get('tasks') or [])} 个任务")
            tag_pool = [str(t) for t in (data.get("tags") or []) if str(t).strip()]
            created, task_count, tag_count = _import_todo(
                db, data, args.project_name, args.split_projects, args.stage, args.dry_run, tag_pool
            )
            for pid, name in created:
                print(f"  + 项目「{name}」 {pid}")
            print(f"  导入任务 {task_count} 个，标签 {tag_count} 个")
        else:
            rows = db.execute("SELECT id, name FROM projects ORDER BY created_at").fetchall()
            if not rows:
                print("数据库中没有项目，请先用 --todo 导入")
                return 1
            created = [(rows[0]["id"], rows[0]["name"])]

        if args.visio:
            files = _visio_files(args.visio)
            target = created[0][0] if created else None
            if args.visio_project:
                row = db.execute(
                    "SELECT id, name FROM projects WHERE id=? OR name=?", (args.visio_project, args.visio_project)
                ).fetchone()
                if not row:
                    print(f"找不到目标项目：{args.visio_project}")
                    return 1
                target = row["id"]
            if not target:
                print("没有可用的目标项目，无法导入拓扑图")
                return 1
            count = _import_visio(db, files, target, args.dry_run)
            print(f"  导入拓扑图 {count} 张 -> 项目 {target}")

        if args.dry_run:
            db.rollback()
            print("dry-run：未写入数据库")
        else:
            db.commit()
            print(f"完成，数据库：{args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
