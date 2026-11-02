"""Sample data for TopoTash — a realistic pre-sales portfolio.

Run: python app.py seed-demo   (safe: skips when projects already exist)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db import dumps, get_db, new_id, utcnow
from services import create_task_record, sync_diagram_nodes

STAGE_RESEARCH = "research"
STAGE_PROPOSAL = "proposal"
STAGE_POC = "poc"
STAGE_BIDDING = "bidding"


def _iso(days: int, hour: int = 18) -> str:
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def _date(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")


def _project(name, customer, stage, status, owner, color, description, industry="", code=""):
    db = get_db()
    pid = new_id("p_")
    now = utcnow()
    db.execute(
        """INSERT INTO projects
           (id, name, code, customer, industry, owner, stage, status, description, color,
            start_date, end_date, todo_config, metadata, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, '{}', '{}', ?, ?)""",
        (pid, name, code, customer, industry, owner, stage, status, description, color,
         _date(-21), _date(30), now, now),
    )
    cid = new_id("c_")
    db.execute(
        "INSERT INTO task_categories(id, project_id, name, color, sort_order, created_at) VALUES (?,?,?,?,?,?)",
        (cid, pid, "默认分类", "#6366f1", 0, now),
    )
    return pid, cid


def _task(pid, cid, title, stage, status="todo", priority=2, due_days=None, description="", tags=None, subtasks=None):
    payload = {
        "title": title,
        "description": description,
        "priority": priority,
        "status": status,
        "stage": stage,
        "category_id": cid,
        "due_date": _iso(due_days) if due_days is not None else None,
        "tags": tags or [],
        "subtasks": [{"title": t, "completed": bool(done)} for t, done in (subtasks or [])],
    }
    return create_task_record(pid, payload, source="manual")


def _shape(node_id, kind, label, x, y, fields=None):
    return {
        "id": node_id, "type": "shape", "kind": kind, "x": x, "y": y, "w": 120, "h": 120,
        "rot": 0, "flipH": False, "flipV": False, "fill": "#5b6cf0", "stroke": "none",
        "strokeWidth": 1.6, "dash": None, "opacity": 1, "fillOpacity": 1, "radius": 10,
        "text": label, "textColor": "#1f2329", "fontSize": 13, "fontFamily": "Microsoft YaHei",
        "bold": True, "italic": False, "textAlign": "center", "textVAlign": "bottom",
        "imgFit": "fill", "image": None, "origRatio": None, "lockRatio": True,
        "fields": [{"k": k, "v": v} for k, v in (fields or [])],
    }


def _connector(cid, start, end, label=""):
    return {
        "id": cid, "type": "connector", "kind": "line",
        "start": {"shapeId": start, "port": "E"}, "end": {"shapeId": end, "port": "W"},
        "custom": False, "points": [], "stroke": "#94a3b8", "strokeWidth": 1.6,
        "dash": None, "arrowStart": False, "arrowEnd": False, "text": label, "flow": "off",
    }


def _diagram(pid, name, kind, description, shapes, edges):
    db = get_db()
    did = new_id("d_")
    now = utcnow()
    content = {
        "app": "topotash", "version": 2,
        "shapes": {s["id"]: s for s in shapes},
        "order": [s["id"] for s in shapes] + [e["id"] for e in edges],
        "groups": {}, "imagePool": {},
    }
    for e in edges:
        content["shapes"][e["id"]] = e
    db.execute(
        """INSERT INTO diagrams
           (id, project_id, name, kind, description, content_json, version, node_count, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (did, pid, name, kind, description, dumps(content), 1, len(shapes), now, now),
    )
    sync_diagram_nodes(did, content)
    return did


def _link_node(did, node_key, task_id, status, diagram_for_task=True):
    db = get_db()
    db.execute(
        "INSERT INTO node_task_links(diagram_id, node_key, task_id, relation, is_primary, note, created_at)"
        " VALUES (?,?,?,'followup',1,'',?)",
        (did, node_key, task_id, utcnow()),
    )
    db.execute(
        "UPDATE diagram_nodes SET followup_status=? WHERE diagram_id=? AND node_key=?",
        (status, did, node_key),
    )
    if diagram_for_task:
        db.execute(
            "INSERT OR IGNORE INTO task_diagrams(task_id, diagram_id, relation, note, created_at)"
            " VALUES (?,?,'related','',?)",
            (task_id, did, utcnow()),
        )


def seed_demo() -> int:
    db = get_db()
    existing = db.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
    if existing:
        return 0

    # ------------------------------------------------------------------ 1 POC
    pid, cid = _project(
        "星海银行 私有云 POC", "星海银行", STAGE_POC, "active", "张伟", "#4f5bd5",
        "客户计划将核心外围系统迁至私有云，先做 3 节点 POC 验证网络与存储性能。",
        industry="金融", code="PS-2026-018",
    )
    t_env = _task(pid, cid, "确认 POC 环境与到货时间", STAGE_POC, priority=0, due_days=2,
                  description="和客户机房确认机柜、电力、带外管理网段与设备到货窗口。",
                  tags=["POC", "环境"], subtasks=[("确认机柜位置", True), ("确认带外网段", False), ("设备到货签收", False)])
    t_net = _task(pid, cid, "POC 网络方案与 VLAN 规划", STAGE_POC, status="doing", priority=1, due_days=4,
                  description="输出 POC 环境的 VLAN、互联地址与安全策略。", tags=["方案", "网络"])
    t_storage = _task(pid, cid, "分布式存储性能压测", STAGE_POC, priority=1, due_days=6,
                      description="fio 4K 随机写 / 顺序读，记录 IOPS 与时延基线。", tags=["POC", "存储"])
    t_doc = _task(pid, cid, "POC 测试报告初稿", STAGE_POC, priority=2, due_days=9, tags=["文档"],
                  subtasks=[("性能数据汇总", False), ("问题清单", False), ("结论与建议", False)])
    t_req = _task(pid, cid, "补充容灾需求调研", STAGE_RESEARCH, status="done", priority=2, due_days=-8,
                  description="确认同城双活 RPO/RTO 要求。", tags=["调研"])
    t_bid = _task(pid, cid, "整理 POC 转商用的配置清单", STAGE_BIDDING, priority=2, due_days=12, tags=["报价"])
    t_prop = _task(pid, cid, "更新私有云技术方案 V2", STAGE_PROPOSAL, status="done", priority=1, due_days=-3,
                   tags=["方案"])

    shapes = [
        _shape("n1", "globe", "互联网", 60, 60, [("带宽", "1Gbps"), ("状态", "online")]),
        _shape("n2", "firewall", "边界防火墙", 230, 60, [("型号", "USG6650E"), ("状态", "online"), ("CPU", "23%")]),
        _shape("n3", "switch", "核心交换机", 400, 60, [("堆叠", "2 台"), ("端口", "48×10GE")]),
        _shape("n4", "server", "计算节点 ×3", 250, 250, [("CPU", "2×6338"), ("内存", "512G"), ("GPU", "2×A100")]),
        _shape("n5", "storage", "分布式存储", 440, 250, [("容量", "120TB"), ("IOPS", "180K")]),
        _shape("n6", "db", "Oracle 集群", 620, 250, [("版本", "19c"), ("RAC", "2 节点")]),
        _shape("n7", "pc", "运维终端", 620, 60, [("网段", "10.10.8.0/24")]),
    ]
    edges = [
        _connector("c1", "n1", "n2", "10G"),
        _connector("c2", "n2", "n3"),
        _connector("c3", "n3", "n4", "25G"),
        _connector("c4", "n3", "n5", "25G"),
        _connector("c5", "n5", "n6", "FC"),
        _connector("c6", "n3", "n7"),
    ]
    did = _diagram(pid, "POC 环境部署图", "deployment",
                   "POC 三节点计算 + 分布式存储，边界经防火墙接入客户核心交换机。", shapes, edges)
    _link_node(did, "n4", t_env, "todo")
    _link_node(did, "n3", t_net, "doing")
    _link_node(did, "n5", t_storage, "todo")

    shapes2 = [
        _shape("n1", "cloud", "私有云平台", 220, 40, [("架构", "IaaS + PaaS")]),
        _shape("n2", "cluster", "管理集群", 60, 220, [("节点", "3"), ("状态", "online")]),
        _shape("n3", "cluster", "业务集群", 240, 220, [("节点", "6"), ("CPU", "62%")]),
        _shape("n4", "storage", "块存储池", 420, 220, [("容量", "200TB")]),
        _shape("n5", "db", "云数据库", 600, 220, [("类型", "MySQL/PG")]),
    ]
    edges2 = [
        _connector("c1", "n1", "n2"), _connector("c2", "n1", "n3"),
        _connector("c3", "n3", "n4"), _connector("c4", "n3", "n5"),
    ]
    _diagram(pid, "私有云逻辑架构", "architecture", "目标态私有云逻辑分区与管理面关系。", shapes2, edges2)

    # -------------------------------------------------------------- 2 方案
    pid2, cid2 = _project(
        "恒达制造 智能工厂网络改造", "恒达制造", STAGE_PROPOSAL, "active", "李娜", "#0d9488",
        "三个厂区网络扁平化改造，生产网 / 办公网 / 安防网三网隔离，新增无线覆盖。",
        industry="制造", code="PS-2026-021",
    )
    _task(pid2, cid2, "厂区现网勘查与拓扑还原", STAGE_RESEARCH, status="done", priority=1, due_days=-10,
          tags=["调研"], subtasks=[("A 厂区", True), ("B 厂区", True), ("C 厂区", True)])
    p2_t1 = _task(pid2, cid2, "生产网 VLAN 与工业协议规划", STAGE_PROPOSAL, status="doing", priority=1, due_days=3,
                  description="Profinet / Modbus 场景下的二层隔离与 QoS。", tags=["方案", "网络"])
    _task(pid2, cid2, "无线覆盖点位设计", STAGE_PROPOSAL, priority=2, due_days=5, tags=["方案", "无线"])
    _task(pid2, cid2, "方案报价与配置清单", STAGE_PROPOSAL, priority=1, due_days=7, tags=["报价"])
    _task(pid2, cid2, "客户技术交流会（方案汇报）", STAGE_PROPOSAL, priority=0, due_days=1, tags=["会议"])
    _task(pid2, cid2, "POC 测试范围确认", STAGE_POC, priority=2, due_days=15, tags=["POC"])

    shapes3 = [
        _shape("n1", "cloud", "集团总部", 60, 40, [("链路", "双线 500M")]),
        _shape("n2", "firewall", "出口防火墙", 240, 40, [("HA", "主备")]),
        _shape("n3", "router", "核心路由", 420, 40, [("协议", "OSPF")]),
        _shape("n4", "switch", "生产网接入", 180, 240, [("VLAN", "10/20/30")]),
        _shape("n5", "switch", "办公网接入", 360, 240, [("VLAN", "100")]),
        _shape("n6", "switch", "安防网接入", 540, 240, [("VLAN", "200")]),
        _shape("n7", "server", "MES 服务器", 700, 240, [("系统", "MES 3.2")]),
    ]
    edges3 = [
        _connector("c1", "n1", "n2"), _connector("c2", "n2", "n3"),
        _connector("c3", "n3", "n4"), _connector("c4", "n3", "n5"),
        _connector("c5", "n3", "n6"), _connector("c6", "n4", "n7"),
    ]
    did3 = _diagram(pid2, "工厂网络逻辑拓扑", "topology",
                    "三网隔离：生产 / 办公 / 安防分别接入核心，MES 位于生产区。", shapes3, edges3)
    _link_node(did3, "n4", p2_t1, "doing")

    # ------------------------------------------------------------ 3 招投标
    pid3, cid3 = _project(
        "市政云 政务云二期扩容", "市大数据局", STAGE_BIDDING, "active", "王强", "#dc2626",
        "二期扩容 40 台服务器与云平台授权，投标截止本月底，需完成技术标与商务标。",
        industry="政府", code="PS-2026-009",
    )
    _task(pid3, cid3, "技术标书应答（网络章节）", STAGE_BIDDING, status="doing", priority=0, due_days=4,
          tags=["标书", "网络"])
    _task(pid3, cid3, "商务报价与折扣审批", STAGE_BIDDING, priority=0, due_days=3, tags=["报价", "审批"])
    _task(pid3, cid3, "资质材料与案例整理", STAGE_BIDDING, priority=1, due_days=5, tags=["标书"],
          subtasks=[("营业执照/资质", True), ("同类案例 3 个", False), ("授权函", False)])
    _task(pid3, cid3, "投标保证金办理", STAGE_BIDDING, priority=1, due_days=6, tags=["流程"])
    _task(pid3, cid3, "开标与讲标演练", STAGE_BIDDING, priority=2, due_days=8, tags=["会议"])

    shapes4 = [
        _shape("n1", "cloud", "政务外网", 40, 40, [("出口", "双链路")]),
        _shape("n2", "firewall", "边界安全区", 200, 40, [("等保", "三级")]),
        _shape("n3", "switch", "核心交换区", 370, 40, [("架构", "双核心")]),
        _shape("n4", "server", "计算资源池", 180, 240, [("节点", "40"), ("CPU", "80%")]),
        _shape("n5", "storage", "集中存储", 360, 240, [("容量", "1PB")]),
        _shape("n6", "db", "政务数据库", 540, 240, [("类型", "达梦/人大金仓")]),
        _shape("n7", "globe", "互联网区", 700, 40, [("隔离", "网闸")]),
    ]
    edges4 = [
        _connector("c1", "n1", "n2"), _connector("c2", "n2", "n3"),
        _connector("c3", "n3", "n4"), _connector("c4", "n3", "n5"),
        _connector("c5", "n5", "n6"), _connector("c6", "n3", "n7"),
    ]
    did4 = _diagram(pid3, "政务云总体架构", "architecture",
                    "政务外网 / 互联网双区隔离，计算、存储、数据库集中池化。", shapes4, edges4)
    _link_node(did4, "n4", _task(pid3, cid3, "确认扩容资源池上架位置", STAGE_BIDDING, priority=2, due_days=10), "todo")

    # ------------------------------------------------------------ 4 调研
    pid4, cid4 = _project(
        "瑞康医药 数据中台选型", "瑞康医药", STAGE_RESEARCH, "paused", "陈晨", "#7c3aed",
        "客户正在做数据中台选型，先进行业务调研与竞品对比，项目因预算暂缓。",
        industry="医药", code="PS-2026-024",
    )
    _task(pid4, cid4, "访谈业务部门（销售 / 供应链）", STAGE_RESEARCH, priority=1, due_days=2, tags=["调研", "会议"])
    _task(pid4, cid4, "梳理数据源与指标口径", STAGE_RESEARCH, priority=1, due_days=5, tags=["调研"])
    _task(pid4, cid4, "竞品对比（阿里 / 华为 / 星环）", STAGE_RESEARCH, priority=2, due_days=8, tags=["方案"])
    _task(pid4, cid4, "输出选型建议书", STAGE_PROPOSAL, priority=2, due_days=14, tags=["文档"])

    db.commit()
    return 4
