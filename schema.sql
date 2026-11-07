-- ============================================================================
-- TopoTash / 拓事 — SQLite 数据库结构
-- 以「项目」为核心：项目 1─N 任务，项目 1─N 拓扑图；
-- 任务 ↔ 拓扑图 多对多；拓扑图节点 ↔ 任务 多对多（节点可标记待跟进）。
-- 执行：python app.py init-db   （或 flask --app app init-db）
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. 项目（售前商机 / 客户项目）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,                 -- UUID，跨表引用
    name        TEXT NOT NULL,                    -- 项目名称，如「XX 银行私有云 POC」
    code        TEXT,                             -- 项目编号 / 商机编号
    customer    TEXT,                             -- 客户名称
    industry    TEXT,                             -- 行业，如 金融 / 制造 / 政府
    owner       TEXT,                             -- 售前负责人
    stage       TEXT NOT NULL DEFAULT 'research'  -- 售前阶段
                CHECK (stage IN ('research','proposal','poc','bidding')),
    status      TEXT NOT NULL DEFAULT 'active'    -- 项目结果
                CHECK (status IN ('active','won','lost','paused')),
    description TEXT NOT NULL DEFAULT '',
    color       TEXT NOT NULL DEFAULT '#5b6cf0',  -- 项目主题色（卡片、时间线）
    start_date  TEXT,                             -- YYYY-MM-DD
    end_date    TEXT,                             -- YYYY-MM-DD
    todo_config TEXT NOT NULL DEFAULT '{}',       -- 任务台的 aiConfig / aiChatHistory 等
    metadata    TEXT NOT NULL DEFAULT '{}',       -- 预留扩展 JSON
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_stage  ON projects(stage);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);

-- ----------------------------------------------------------------------------
-- 2. 任务分类（对应任务台内部「项目/项目分类」，是项目内的工作流分组）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_categories (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#6366f1',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_categories_project ON task_categories(project_id);

-- ----------------------------------------------------------------------------
-- 3. 任务
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category_id  TEXT REFERENCES task_categories(id) ON DELETE SET NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    priority     INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 0 AND 3),
    status       TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','done')),
    stage        TEXT NOT NULL DEFAULT 'research'  -- 任务所属售前阶段
                 CHECK (stage IN ('research','proposal','poc','bidding')),
    due_date     TEXT,                             -- ISO 8601（含时间）
    recur        TEXT,                             -- daily/weekly/monthly/quarterly/yearly
    recur_day    INTEGER,                          -- 周几(0-6) 或 几号(1-31)
    sort_order   REAL NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'manual',   -- manual | ai | diagram | import
    completed_at TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_stage   ON tasks(stage);
CREATE INDEX IF NOT EXISTS idx_tasks_due     ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category_id);

-- ----------------------------------------------------------------------------
-- 4. 子任务（任务台的 subtasks[]）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subtasks (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0,1)),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id, sort_order);

-- ----------------------------------------------------------------------------
-- 5. 标签（项目内共享标签池）与任务-标签关联
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#64748b',
    created_at  TEXT NOT NULL,
    UNIQUE (project_id, name)
);
CREATE INDEX IF NOT EXISTS idx_tags_project ON tags(project_id);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id  TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_task_tags_tag ON task_tags(tag_id);

-- ----------------------------------------------------------------------------
-- 6. 拓扑图
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diagrams (
    id           TEXT PRIMARY KEY,
    project_id   TEXT REFERENCES projects(id) ON DELETE CASCADE,  -- NULL = 仅存放在拓扑图库
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'topology',   -- topology | architecture | deployment | other
    description  TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL DEFAULT '{"app":"topotash","version":2,"shapes":{},"order":[],"groups":{},"imagePool":{}}',
    version      INTEGER NOT NULL DEFAULT 0,          -- 每次保存自增，便于冲突判断
    node_count   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_diagrams_project ON diagrams(project_id, updated_at DESC);

-- ----------------------------------------------------------------------------
-- 7. 拓扑图节点（从 content_json 解析出的索引，供跨图检索 / 关联 / 聚合）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diagram_nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    diagram_id      TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
    node_key        TEXT NOT NULL,                 -- 画布 shape id，如 n12
    label           TEXT NOT NULL DEFAULT '',
    kind            TEXT,                          -- server / switch / firewall ...
    x               REAL,
    y               REAL,
    w               REAL,
    h               REAL,
    followup_status TEXT NOT NULL DEFAULT 'none'   -- 节点跟进状态
                    CHECK (followup_status IN ('none','todo','doing','done')),
    note            TEXT NOT NULL DEFAULT '',
    synced_at       TEXT NOT NULL,
    UNIQUE (diagram_id, node_key)
);
CREATE INDEX IF NOT EXISTS idx_nodes_diagram ON diagram_nodes(diagram_id);
CREATE INDEX IF NOT EXISTS idx_nodes_followup ON diagram_nodes(followup_status);

-- ----------------------------------------------------------------------------
-- 8. 节点-任务关联（一个节点可挂多个任务，is_primary 指定「主任务」）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS node_task_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    diagram_id  TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
    node_key    TEXT NOT NULL,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    relation    TEXT NOT NULL DEFAULT 'followup',  -- followup | reference | blocker
    is_primary  INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (diagram_id, node_key, task_id)
);
CREATE INDEX IF NOT EXISTS idx_ntl_node ON node_task_links(diagram_id, node_key);
CREATE INDEX IF NOT EXISTS idx_ntl_task ON node_task_links(task_id);

-- ----------------------------------------------------------------------------
-- 9. 任务-拓扑图关联（任务级：确认 POC 环境 ↔ POC 部署图）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_diagrams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    diagram_id  TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
    relation    TEXT NOT NULL DEFAULT 'related',   -- related | reference | output
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (task_id, diagram_id)
);
CREATE INDEX IF NOT EXISTS idx_td_task ON task_diagrams(task_id);
CREATE INDEX IF NOT EXISTS idx_td_diagram ON task_diagrams(diagram_id);

-- ----------------------------------------------------------------------------
-- 10. 操作日志（可选，用于项目动态）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,                     -- project | task | diagram | node
    entity_id   TEXT,
    action      TEXT NOT NULL,                     -- create | update | delete | link
    detail      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_project ON activity_log(project_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 11. 元信息（schema 版本，方便后续迁移）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- 12. 全局设置（AI 配置等，与项目无关，一处配置全局可用）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- 13. AI 会话（全局 AI 助手；project_id 仅表示会话创建时的上下文，可选）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT '新对话',
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_conv_updated ON ai_conversations(updated_at DESC);

-- ----------------------------------------------------------------------------
-- 14. AI 消息（user / assistant / tool，含 function calling 原始信息）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,                -- system | user | assistant | tool
    content         TEXT NOT NULL DEFAULT '',
    tool_calls      TEXT NOT NULL DEFAULT '',     -- assistant 的 tool_calls JSON
    tool_call_id    TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',     -- tool 名称
    meta            TEXT NOT NULL DEFAULT '{}',   -- 展示用附加信息（错误标记等）
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_msg_conv ON ai_messages(conversation_id, id);

-- ----------------------------------------------------------------------------
-- 15. AI 待确认动作（AI 只生成草稿，用户确认后才真正写库）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_actions (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,                -- create_project | update_project | delete_project
                                                  -- create_task | update_task | delete_task
    payload         TEXT NOT NULL DEFAULT '{}',   -- 可编辑字段 + 目标 id + 摘要
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','applied','cancelled')),
    result          TEXT NOT NULL DEFAULT '{}',   -- 执行结果（项目/任务 id、名称）
    created_at      TEXT NOT NULL,
    applied_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_actions_conv ON ai_actions(conversation_id, status);

-- ----------------------------------------------------------------------------
-- 16. 项目设备清单（方案级 BOM）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id          TEXT PRIMARY KEY,                  -- d_xxx
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'other'
                CHECK (category IN ('server','storage','network','security','software','other')),
    brand       TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    spec        TEXT NOT NULL DEFAULT '',          -- 关键参数 / 配置
    quantity    INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    unit        TEXT NOT NULL DEFAULT '台',         -- 台 / 套 / 节点 / 个 / 块
    status      TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','selected','quoted','ordered','delivered')),
    unit_price  REAL,                              -- 可空；空值不参与合计
    currency    TEXT NOT NULL DEFAULT 'CNY',
    vendor      TEXT NOT NULL DEFAULT '',
    owner       TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    sort_order  REAL NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_project ON devices(project_id, sort_order, name);
CREATE INDEX IF NOT EXISTS idx_devices_category ON devices(project_id, category);
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(project_id, status);

-- ----------------------------------------------------------------------------
-- 17. 设备-拓扑节点关联（多对多；quantity 是本节点部署数量）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_node_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    diagram_id  TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
    node_key    TEXT NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (device_id, diagram_id, node_key)
);
CREATE INDEX IF NOT EXISTS idx_dnl_node ON device_node_links(diagram_id, node_key);
CREATE INDEX IF NOT EXISTS idx_dnl_device ON device_node_links(device_id);

-- ----------------------------------------------------------------------------
-- 18. 全局设备模板（跨项目复用的设备预设，不绑定项目和数量）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_templates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'other'
                CHECK (category IN ('server','storage','network','security','software','other')),
    brand       TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    spec        TEXT NOT NULL DEFAULT '',
    unit        TEXT NOT NULL DEFAULT '台',
    unit_price  REAL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_templates_key
    ON device_templates(name, brand, model);
CREATE INDEX IF NOT EXISTS idx_device_templates_category ON device_templates(category, name);

INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', '5');
