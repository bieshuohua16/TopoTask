# TopoTash 多用户 / 团队 / 权限 与线上部署方案

| 项目 | 内容 |
|---|---|
| 文档版本 | 1.3 |
| 日期 | 2026-11-09 |
| 状态 | 待评审（上线范围与设备模板团队共享已确认） |
| 适用代码版本 | `0e2bd19`（schema v5，65 个 API、7 个 HTML 页面、172 个测试） |
| 目标读者 | 项目负责人、后端/前端实现者、运维 |

**变更记录**

| 版本 | 变更 |
|---|---|
| 1.0 | 初版：完全隔离（A）、管理员建号、AI 全局配置、宝塔部署 |
| 1.1 | 评审后调整：① 隔离升级为 **A+（完全隔离 + 项目级显式共享）**；② 团队 leader 增加**本团队成员管理**与**项目归属分配**；③ 确认已有备案域名；④ 新增第 14 节「实现后可达成的能力」 |
| 1.2 | 代码重构后复核：① 基线更新为 schema v5 / 65 API / 172 测试；② 新增**设备清单、设备模板库、节点-设备关联**的权限设计；③ 设备模板写权限定为**仅管理员**；④ 保留**本地免登录模式**；⑤ 迁移目标由 v4 调整为 **v6**；⑥ 补充生产运行基线（gunicorn/wsgi、SSE、32MB、健康检查、备份）；⑦ 废弃 1.1 的「先上线无权限版本」做法 |
| 1.3 | 设备模板权限调整：① 模板改为**团队共享**，`device_templates` 增加 `team_id`；② **本团队所有成员与负责人**均可新增/编辑/删除/CSV 导入；③ **管理员可查看全部团队的模板，并看到归属团队**，但对模板**只读**；④ 模板唯一键改为 `(team_id, name, brand, model)`，CSV 重复判断按团队内 `(brand, model)`；⑤ 迁移时存量模板归入默认团队 |

---

## 0. 摘要与决策记录

本文档定义把 TopoTash 从「单人本地工具」升级为「多人云端协作工具」的设计，包括账号、团队、权限隔离，以及在公有云宝塔（BT Panel）环境上的部署方案。

### 0.1 当前代码事实（已核对）

- 技术栈：Flask 3 + SQLite（WAL）+ 原生 JS；运行依赖仍只有 `Flask>=3.0,<4`，**没有 gunicorn / wsgi 入口**；
- **没有任何认证代码**（全仓库不存在 `session` / `login` / `password` / `current_user` 实现）；
- **65 个 API 路由**：`projects` 9、`tasks` 11、`diagrams` 16、`devices` 7、`device-templates` 7、`views` 4、`ai` 11；
- **7 个 HTML 页面 + `/healthz` + `/static/**`**，共 9 条页面规则；
- **172 个 `unittest` 用例**，全部通过未登录的 `test_client` 调用接口；
- **schema 已是 v5**：在 v3 基础上增加了 `devices`、`device_node_links`、`device_templates`；
- `projects.owner` 仍是**自由文本**（`schema.sql:19`），不是账号；
- `diagrams.project_id` 允许 `NULL`（库内未绑定图纸，`schema.sql:116`）；
- AI 配置是**全局单份**，存放在 `app_settings`（`services_ai.py:110`），API Key 下发时已脱敏；
- `device_templates` 当前是**全局共享**表，没有 `team_id` / `owner_user_id`；v6 将增加 `team_id`，改为团队共享；
- 启动器使用 Flask 开发服务器（`start_topotash.py:214`），入口 `app = create_app()` 在导入时就执行建库/迁移；
- `SECRET_KEY` 有硬编码兜底（`app.py:35`）；
- `/healthz` 返回数据库绝对路径（`app.py:135`），本地启动器依赖该字段区分实例；
- 生产代码中涉及 `projects` / `tasks` / `diagrams` / `devices` 的 SQL 约 **114 处**（`services_ai.py` 23、`services_devices.py` 18、`api/diagrams.py` 18、`services.py` 21、`api/views.py` 14、`api/projects.py` 9、`api/tasks.py` 6、`app.py` 4、`db.py` 1）。

### 0.2 与 v1.1 的主要差异

| 维度 | v1.1 口径 | 当前实际 | 本版处理 |
|---|---|---|---|
| Schema | v3 → v4 | 已是 **v5** | 迁移目标改为 **v6**，保留设备表 |
| API | 47 个 | **65 个** | 权限标注覆盖新增 18 个接口 |
| 页面 | 7 个路由 | **7 个 HTML 页面**，新增 `/device-templates` 与项目「设备清单」标签页 | 登录/权限/用户菜单覆盖新页面 |
| 数据查询 | 约 81 处 | 约 **114 处** | `visible_project_sql` 必须覆盖 devices |
| 模板资源 | 无 | 新增**设备模板库** | 模板改为**团队共享**：本团队成员/负责人可编辑，管理员全局只读并可查看归属团队（D8） |
| 测试 | 153 个 | **172 个**，全部未登录 | 测试基座改为「自动登录管理员」，否则无法回归 |
| 本地形态 | 保留 Windows 启动器 | 仍为免登录 | 保留**本地免登录模式**（D9），线上强制登录 |
| 部署前置 | P0 可先上线无权限版本 | 无认证直接公网不可接受 | **废弃该做法**，认证纳入 P0 范围 |

### 0.3 决策记录

| # | 决策 | 取值 | 理由 |
|---|---|---|---|
| D1 | 隔离强度 | **A+：完全隔离 + 项目级显式共享** | 售前商机含客户与报价信息，默认隔离；保留「拉同事看一个项目」的能力 |
| D2 | 并发规模 | **很少**（≤ 10 人同时在线） | 继续用 SQLite，不迁移 PostgreSQL |
| D3 | 账号来源 | **管理员建账号**；团队 leader 可在本团队内建号、停用、重置密码（不能创建 leader / admin） | 管理员不必成为人事瓶颈，同时限制提权 |
| D4 | AI 配置 | **管理员全局唯一**，其他角色只读脱敏信息 | 与现状一致，成本与 Key 由管理员统管 |
| D5 | 用户与团队 | **一人一团队**（`users.team_id`），角色 `admin/leader/member` | 简化查询与 UI；跨团队需求出现时再升级（附录 C） |
| D6 | 会话实现 | 签名 Cookie + `users.session_epoch`，不建会话表 | 每个请求本来就要取用户做鉴权，校验 epoch 零额外查询 |
| D7 | 部署形态 | 公有云 + 宝塔（Python 项目管理器 + 网站反代 + Let's Encrypt） | 符合现有运维习惯，无 Docker 依赖 |
| D8 | 设备模板权限 | **团队共享**：`device_templates.team_id` 指向所属团队；**本团队所有成员与负责人**可新增/编辑/删除/CSV 导入；**管理员可查看全部团队模板及归属团队，但对模板只读** | 模板是团队内的共享预设，团队自管更灵活；管理员保留跨团队可见性用于审计与排障，避免误改其他团队的模板 |
| D9 | 本地离线模式 | **保留免登录本地模式**，通过 `TOPOTASH_LOCAL_MODE=1` 开启，仅允许回环地址 | 不破坏 `首次启动.bat` 的双击即用体验；线上由环境变量强制关闭 |
| D10 | 测试认证 | 测试基座自动创建并登录管理员；401/越权用例单独建未登录 client | 保证 172 个既有用例继续有效，同时不削弱认证测试 |

### 0.4 明确不做（非目标）

1. 自助注册、邮箱验证、邀请链接、找回密码邮件（管理员或 leader 重置代替）；
2. **跨团队**共享、任务级 / 时间窗 / 可撤销预约等完整 ACL（仅支持**团队内、项目级、常驻**授权：查看 / 编辑两档）；
3. 企业微信 / 钉钉 / SSO 登录；
4. 操作审计报表与导出（仅保留 `activity_log` 的 actor 字段）；
5. 数据库迁移到 PostgreSQL、多实例水平扩展；
6. 移动端专门适配、国际化；
7. 跨团队复制/共享设备模板（模板只在本团队内可见可编辑；管理员只读查看全局，不做跨团队复制）；
8. 管理员代管设备模板（当前按 D8 只读；如后续需要放开，只需调整 `require_template_write`）；
9. 设备清单的审批流、报价版本管理。

---

## 1. 角色与术语

| 角色 | 标识 | 可见范围 | 说明 |
|---|---|---|---|
| 系统管理员 | `users.role = 'admin'` | **全部**团队全部项目与全部设备模板（只读） | 建团队、建账号、配 AI、可跨团队移动项目；可查看模板归属团队，但不编辑模板 |
| 团队负责人 | `users.role = 'leader'` | **本团队**全部项目 + 被共享的 | 可查看/编辑/删除本团队任何项目；可**建/停用本团队成员、重置密码**；可**分配项目归属**、发起共享；可维护**本团队设备模板**；不可跨团队，不可创建 leader / admin |
| 团队成员 | `users.role = 'member'` | **自己的项目** + **被共享给自己的项目** | 看不到同团队其他人的项目，除非被显式共享；可维护**本团队设备模板** |

术语：

- **可见域（visibility scope）**：某用户有权看到的一组项目 ID 集合。
  - 成员 = 自己 `owner_user_id` 的项目 ∪ `project_members` 中被授权的项目；
  - 负责人 = 本团队全部项目（无需共享记录）；
  - 管理员 = 全部。
- **归属（ownership）**：`projects.owner_user_id` 指向创建者或被指派者。**权限只看归属、团队与共享表，不看 `projects.owner` 文本字段**。
- **共享（share）**：`project_members` 中的一条记录，表示某成员对某项目的**常驻**授权，`access = 'view' | 'edit'`。仅限同团队、仅限项目级。
- **库内图纸**：`diagrams.project_id IS NULL` 的图纸，归属由 `diagrams.owner_user_id` 决定，不参与项目共享。
- **项目设备**：`devices.project_id` 必填，权限完全继承所属项目，不设独立归属。
- **团队设备模板**：`device_templates.team_id` 指向所属团队。**本团队所有成员与负责人**均可新增/编辑/删除/CSV 导入；其他团队不可见；管理员可查看全部团队的模板及归属团队，但对模板**只读**。

---

## 2. 领域模型

### 2.1 关系

```
teams 1 ── N users（team_id，admin 可为 NULL）
teams 1 ── N projects（team_id）
users 1 ── N projects（owner_user_id，创建/被指派）
projects N ── N users（project_members：项目级共享，view / edit）
users 1 ── N diagrams（owner_user_id，仅库内图纸有意义）
users 1 ── N ai_conversations（user_id）
projects 1 ── N tasks / diagrams / devices / task_categories / tags / activity_log
devices  N ── N diagram_nodes（device_node_links，同一项目内）
teams 1 ── N device_templates（team_id；团队内可编辑，admin 全局只读）
```

关键性质：任务、子任务、标签、图纸节点、节点-任务关联、任务-图纸关联、设备、设备-节点关联全部通过 `project_id` 级联，**因此只要控制「项目」这一层的可见性，其下所有数据自动继承**。这是本方案能保持改动可控的根本原因。

### 2.2 归属规则

| 资源 | 归属字段 | 由谁决定 | 备注 |
|---|---|---|---|
| 项目 | `projects.team_id` + `owner_user_id` | 创建者即 owner；team = 创建者的团队（管理员可选团队） | `owner` 文本保留为「售前负责人」展示名，不参与鉴权 |
| 项目共享 | `project_members(project_id, user_id, access)` | owner、本团队 leader、管理员 | 仅同团队成员；`view` 只读，`edit` 可改 |
| 任务 | 无独立归属 | 随所属项目 | `tasks.project_id` 必需 |
| 图纸（绑定项目） | 随项目 | 创建时的项目 | 项目被删除时级联 |
| 图纸（库内） | `diagrams.owner_user_id` | 创建者 | 成员仅见自己的；负责人见本团队成员的 |
| 设备 | 无独立归属 | 随所属项目 | `devices.project_id` 必需，权限继承项目 |
| 设备-节点关联 | 随设备与图纸 | 两端必须同项目 | 写操作要求项目写权限 |
| 团队设备模板 | `device_templates.team_id` | 创建时取当前用户的团队 | 本团队成员/负责人可编辑；其他团队不可见；管理员全局只读并显示归属团队 |
| 任务分类 / 标签 | 随项目 | — | 不变 |
| AI 会话 | `ai_conversations.user_id` | 创建者 | 每人只看自己的会话 |
| AI 草稿动作 | 随会话 | — | 确认时**重新**校验目标项目的写权限 |

---

## 3. 数据库设计（schema v5 → v6）

### 3.1 新增表

```sql
-- ---------------------------------------------------------------------------
-- 100. 团队
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 101. 账号
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                   TEXT PRIMARY KEY,
    email                TEXT NOT NULL COLLATE NOCASE UNIQUE,  -- 登录名
    display_name         TEXT NOT NULL,
    password_hash        TEXT NOT NULL,                        -- werkzeug scrypt
    role                 TEXT NOT NULL DEFAULT 'member'
                         CHECK (role IN ('admin','leader','member')),
    team_id              TEXT REFERENCES teams(id) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','disabled')),
    must_change_password INTEGER NOT NULL DEFAULT 1 CHECK (must_change_password IN (0,1)),
    session_epoch        INTEGER NOT NULL DEFAULT 0,            -- 递增即全端下线
    last_login_at        TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    -- 只有管理员可以没有团队；leader/member 必须属于一个团队
    CHECK (role = 'admin' OR team_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_users_team ON users(team_id, status);

-- ---------------------------------------------------------------------------
-- 102. 项目级共享（A+ 隔离模型的唯一例外来源）
--     只在同团队内有效；view = 只读，edit = 可编辑
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access     TEXT NOT NULL DEFAULT 'view' CHECK (access IN ('view','edit')),
    granted_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_pm_user ON project_members(user_id, project_id);

-- ---------------------------------------------------------------------------
-- 103. 登录失败限流（按 IP 与账号双维度）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS login_throttle (
    key              TEXT PRIMARY KEY,     -- 'ip:1.2.3.4' 或 'email:a@b.c'
    failures         INTEGER NOT NULL DEFAULT 0,
    first_failure_at TEXT,
    locked_until     TEXT,
    updated_at       TEXT NOT NULL
);
```

> `device_templates` 在 v5 已存在，本节不重建该表，只在 3.2 增加 `team_id` 并调整唯一索引。

### 3.2 现有表增加字段

```sql
ALTER TABLE projects         ADD COLUMN team_id       TEXT REFERENCES teams(id);
ALTER TABLE projects         ADD COLUMN owner_user_id TEXT REFERENCES users(id);
ALTER TABLE diagrams         ADD COLUMN owner_user_id TEXT REFERENCES users(id);
ALTER TABLE ai_conversations ADD COLUMN user_id       TEXT REFERENCES users(id);
ALTER TABLE activity_log     ADD COLUMN actor_user_id TEXT REFERENCES users(id);
ALTER TABLE device_templates ADD COLUMN team_id       TEXT REFERENCES teams(id);

CREATE INDEX IF NOT EXISTS idx_projects_team  ON projects(team_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_diagrams_owner ON diagrams(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_ai_conv_user   ON ai_conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_templates_team ON device_templates(team_id, category, name);

-- 模板唯一性从「全局」改为「团队内」：不同团队可以各自维护同名同型号模板
DROP INDEX IF EXISTS idx_device_templates_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_templates_team_key
    ON device_templates(team_id, name, brand, model);

UPDATE app_meta SET value = '6' WHERE key = 'schema_version';
```

说明：

- SQLite 的 `ALTER TABLE ADD COLUMN` 不能加 `NOT NULL`（无默认值），因此 `team_id` / `owner_user_id` 在数据库层允许 NULL，**由应用层保证新增数据必有值**，并用测试兜底（见 10.3 TC-09）。
- `devices` 与 `device_node_links` **不需要新增归属字段**：`devices.project_id` 已经决定权限；`device_node_links` 两端都必须在同一项目。
- `device_templates` **需要新增 `team_id`**：数据库层允许 NULL 以兼容存量表，迁移时把存量模板全部回填到默认团队；应用层创建模板时强制写入当前用户的 `team_id`。管理员没有团队，因此**不能创建模板**。
- 模板唯一键必须同步改为 `(team_id, name, brand, model)`；否则 A 团队建了某型号模板，B 团队无法再建同名模板。CSV 导入的重复判断也从全局 `(brand, model)` 改为**当前团队内** `(brand, model)`。
- `diagrams.team_id` 不加：绑定项目的图纸通过 JOIN 项目判定；库内图纸通过 `owner_user_id → users.team_id` 判定。
- **`schema.sql` 也要同步到 v6**：新库直接按 v6 建表（`device_templates.team_id`、新的团队唯一索引、`schema_version = 6`）；迁移函数只负责把已有 v5 库升级到 v6，避免新库再走一遍 `ALTER TABLE`。
- 迁移目标版本由 v4 改为 **v6**，因为设备模块已经把 `schema_version` 推进到 5；不要回退到 v4，否则设备表会被误判为「未来版本」。

### 3.3 迁移脚本设计（`db.py`）

在 `migrate_schema()` 中新增一个受版本号保护的函数，风格与现有迁移一致：

```python
def migrate_schema(conn: sqlite3.Connection) -> None:
    _migrate_diagrams_project_nullable(conn)
    _migrate_v6_teams_and_users(conn)


def _migrate_v6_teams_and_users(conn: sqlite3.Connection) -> None:
    version = int(_schema_version(conn) or 0)
    if version >= 6:
        return
    _backup_before_migration(conn)      # 用 conn.backup() 写到 topotash.db.bak-v5-<ts>
    conn.executescript(V6_SCHEMA)        # 3.1 + 3.2 的 DDL
    _bootstrap_default_team_and_admin(conn)   # 见 3.4
    _backfill_ownership(conn)                 # 见 3.5
    conn.execute("PRAGMA foreign_key_check")  # 有违规就抛错回滚
    conn.commit()
```

要点：

1. **迁移前必须备份**，用 SQLite 官方备份 API（`source.backup(target)`），不要直接拷 `.db` 文件（WAL 模式下未 checkpoint 时拷贝会丢数据）。
2. 迁移必须**幂等**：以 `app_meta.schema_version` 为准，且 DDL 全部 `IF NOT EXISTS`；重复执行不改变结果。
3. **启动时自动迁移要可控**：当前 `create_app()` 在导入时就执行 `ensure_schema(app)`。生产需要增加环境变量守卫：
   ```python
   if os.environ.get("TOPOTASH_AUTO_MIGRATE", "1") == "1":
       ensure_schema(app)
   ```
   生产设置 `TOPOTASH_AUTO_MIGRATE=0`，由部署流程手工执行一次迁移，避免多 worker 并发 DDL。
4. 失败必须整体回滚，绝不能留下半迁移状态。`conn.executescript` 内部会隐式提交，因此 DDL 用显式事务包装：`BEGIN` → DDL → `COMMIT`，异常时 `ROLLBACK`。
5. 迁移后必须校验设备数据：`SELECT COUNT(*) FROM devices` 与迁移前一致；`device_node_links` 全部能 JOIN 到设备与图纸；`device_templates` 数量不变且 `team_id` 全部非空。

### 3.4 首次迁移的引导数据

迁移完成后若 `users` 为空，创建初始管理员，顺序：

1. 环境变量 `TOPOTASH_ADMIN_EMAIL`（必填）与 `TOPOTASH_ADMIN_PASSWORD`（可选）；
2. 若未提供密码，生成 16 位随机密码，**在标准输出/日志打印一次**，并置 `must_change_password = 1`；
3. 创建团队「默认团队」；
4. 管理员 `team_id = NULL`，`role = 'admin'`。

随后删除临时环境变量（文档要求运维在首次启动后清除 `TOPOTASH_ADMIN_PASSWORD`）。

### 3.5 存量数据回填

| 数据 | 回填规则 |
|---|---|
| 全部 `projects` | `team_id` = 默认团队；`owner_user_id` = 初始管理员；`owner` 文本保持原样 |
| `diagrams.project_id IS NULL` | `owner_user_id` = 初始管理员 |
| 全部 `ai_conversations` | `user_id` = 初始管理员 |
| `activity_log` | `actor_user_id` 留 NULL（历史数据无操作者，不做伪造） |
| `devices` | 不需要新增字段；`project_id` 已存在，迁移后自动随项目鉴权 |
| `device_node_links` | 不需要新增字段；迁移后校验两端项目一致 |
| `device_templates` | `team_id` = 默认团队；模板数量与内容不变，迁移后由默认团队成员/负责人接管维护 |

这样迁移后行为与迁移前**完全等价**（管理员能看到一切），用户可以立刻验证数据无损，再逐步建团队、分账号、改归属。

> 注意：存量模板归入默认团队后，管理员对模板只读；需要先在默认团队下创建 leader 或 member 账号，才能继续维护这些模板。这是 D8「团队自管、管理员只读」的直接结果，上线引导步骤中要写清楚。

### 3.6 不变量（由测试保障）

| 编号 | 不变量 |
|---|---|
| INV-1 | 除 `admin` 外，每个 `active` 用户都有 `team_id` |
| INV-2 | 每个 `project` 的 `team_id` 与 `owner_user_id` 均非空（v6 后新建） |
| INV-3 | `owner_user_id` 指向的用户必须属于项目的 `team_id`（转移项目时同步处理） |
| INV-4 | 每个 `ai_conversations` 有 `user_id` |
| INV-5 | `diagrams.project_id IS NULL` 时 `owner_user_id` 非空 |
| INV-6 | `project_members` 中的用户必须与项目属于同一团队（共享不跨团队） |
| INV-7 | `project_members` 不记录项目 owner 本人，也不记录本团队 leader（其权限已天然覆盖） |
| INV-8 | 用户被移出/更换团队时，其在该团队项目上的共享记录必须一并清除 |
| INV-9 | 每个 `devices.project_id` 必须存在；设备-节点关联两端的项目必须一致 |
| INV-10 | `device_templates` 的写操作只能来自该模板所属团队的成员/负责人；管理员对模板只读 |
| INV-11 | `TOPOTASH_LOCAL_MODE=1` 只允许本地启动器使用，生产环境必须为未设置 |
| INV-12 | 每个 `device_templates.team_id` 必须非空且指向存在的团队；模板唯一键在团队内生效 |

---

## 4. 权限模型

### 4.1 权限矩阵

> 未出现在下表「自己的 / 被共享 / 本团队」中的项目，对该角色**一律不可见**（列表不出现、直接访问 404）。

| 操作 | 成员·自己的项目 | 成员·被共享（查看） | 成员·被共享（编辑） | 负责人·本团队 | 管理员 |
|---|---|---|---|---|---|
| 查看项目列表 / 详情 / 统计 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 查看任务、图纸、节点、关联、**设备清单** | ✅ | ✅ | ✅ | ✅ | ✅ |
| 新建项目 | ✅（owner=自己） | — | — | ✅（可选 owner） | ✅（必选团队） |
| 编辑项目字段 / 任务 / 图纸内容 | ✅ | ❌ | ✅ | ✅ | ✅ |
| **编辑设备 / 关联设备到节点 / 导出设备 CSV** | ✅ | ❌ | ✅ | ✅ | ✅ |
| 删除任务 / 子任务 / 图纸 / **设备** | ✅ | ❌ | ✅ | ✅ | ✅ |
| **删除项目本体** | ✅ | ❌ | ❌ | ✅ | ✅ |
| **管理项目共享**（加人/减人/改档位） | ✅ | ❌ | ❌ | ✅ | ✅ |
| **转移项目归属**（换 owner） | ❌ | ❌ | ❌ | ✅ 本团队内 | ✅ |
| 跨团队移动项目 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 团队名册查看 | ✅ 本团队 | ✅ | ✅ | ✅ 本团队 | ✅ 全部 |
| **团队成员管理**（建号 / 停用 / 重置密码） | ❌ | ❌ | ❌ | ✅ 仅本团队 | ✅ |
| **提升为 leader、新建/删除团队** | ❌ | ❌ | ❌ | ❌ | ✅ |
| **设备模板（团队级）** | 见 4.1.1 | 见 4.1.1 | 见 4.1.1 | 见 4.1.1 | 见 4.1.1 |
| AI 配置（读脱敏） | ✅ | ✅ | ✅ | ✅ | ✅ |
| AI 配置（写）、连接测试 | ❌ | ❌ | ❌ | ❌ | ✅ |
| AI 会话 | 仅自己 | 仅自己 | 仅自己 | 仅自己 | 仅自己 |
| 全局搜索 | 自己 + 被共享 | — | — | 本团队 | 全部 |

#### 4.1.1 设备模板权限（团队级）

设备模板不随项目，而是随团队；因此单独列出：

| 操作 | 团队成员 | 团队负责人 | 管理员 |
|---|---|---|---|
| 查看模板 | ✅ 本团队 | ✅ 本团队 | ✅ 全部团队（可筛选） |
| 下载 CSV 样例 | ✅ | ✅ | ✅ |
| 查看**其他团队**模板及归属团队 | ❌ | ❌ | ✅ |
| 新增 / 编辑 / 删除**本团队**模板 | ✅ | ✅ | ❌（只读） |
| CSV 导入到**本团队** | ✅ | ✅ | ❌（只读） |
| 新增 / 编辑 / 删除**其他团队**模板 | ❌ | ❌ | ❌ |

说明：

- 模板的「归属团队」由创建者的 `team_id` 决定，创建后**不随人员调动而迁移**；人员换团队后，只能编辑新团队的模板。
- 管理员默认没有 `team_id`，且 `require_template_write` 对 admin 直接拒绝，因此不能创建/编辑模板；其价值是**跨团队可见性与归属识别**，便于排障与审计。
- 如果后续需要管理员代管，只需放开 `require_template_write` 中对 admin 的限制，不需要改表结构。

**三处刻意收紧的设计**：

1. 被共享的 `edit` 用户**不能删除项目本体、不能管理共享、不能转移归属**——他能改内容，但不能把项目「带走」或「锁死」。
2. 共享**只在同团队内生效**，且**不能共享给自己以外的人**；leader/admin 发起共享也要校验目标用户与项目同团队。
3. **设备模板按团队隔离**：本团队所有成员/负责人都能编辑，其他团队不可见；管理员跨团队只读，避免误改别人团队的预设。

### 4.2 判定规则（单一实现，四处复用）

```python
# access.py（新增，唯一权限真相来源）
def current_user() -> dict | None: ...

def _share_access(project_id, user_id) -> str | None:
    """返回 'view' / 'edit' / None。走 project_members 主键索引，代价可忽略。"""
    row = get_db().execute(
        "SELECT access FROM project_members WHERE project_id=? AND user_id=?",
        (project_id, user_id),
    ).fetchone()
    return row["access"] if row else None

def can_read(user, project) -> bool:
    if user["role"] == "admin":   return True
    if user["role"] == "leader":  return project["team_id"] == user["team_id"]
    if project["owner_user_id"] == user["id"]: return True
    return _share_access(project["id"], user["id"]) is not None

def can_write(user, project) -> bool:
    """编辑内容：owner / 本团队 leader / admin / 被共享为 edit。"""
    if user["role"] in ("admin", "leader"):
        return can_read(user, project)
    if project["owner_user_id"] == user["id"]: return True
    return _share_access(project["id"], user["id"]) == "edit"

def can_manage(user, project) -> bool:
    """项目级管理：删除项目、转移归属、管理共享。被共享的 edit 用户不在此列。"""
    if user["role"] in ("admin", "leader"):
        return can_read(user, project)
    return project["owner_user_id"] == user["id"]

def visible_project_sql(user, alias="p") -> tuple[str, list]:
    """返回可直接拼进 WHERE 的片段与参数，供所有跨项目查询使用。"""
    if user["role"] == "admin":   return "1=1", []
    if user["role"] == "leader":  return f"{alias}.team_id = ?", [user["team_id"]]
    return (
        f"({alias}.owner_user_id = ? OR EXISTS (SELECT 1 FROM project_members pm"
        f" WHERE pm.project_id = {alias}.id AND pm.user_id = ?))",
        [user["id"], user["id"]],
    )

def require_project(project_id, need="read") -> dict:   # read / write / manage，越权抛 404
def require_admin() -> dict:                           # 越权抛 403
```

原则：

1. **默认拒绝**：所有跨项目查询必须显式调用 `visible_project_sql()`；单项目路由必须显式调用 `require_project()`。忘记调用会报错/查空，而不是泄露。
2. **不在 114 处手写权限条件**：手写必然漏，且新增接口时无人察觉。集中式函数 + 针对性泄露测试是唯一可靠做法。
3. **三个判定层级，不要混用**：
   - `can_read`：能看到（含被共享 view）；
   - `can_write`：能改内容（含被共享 edit）；
   - `can_manage`：能改项目本身（删除项目、换 owner、管共享）——**只有 owner / leader / admin**。
4. **错误语义**：
   - 访问不属于自己的项目/图纸/设备/AI 会话 → **404**（不泄露对象存在性）；
   - 调用管理员专属接口 → **403**；
   - 未登录 → **401**（API）/ 302 跳 `/login`（页面）。

### 4.3 设备与设备模板的专用判定

新增三个解析器，全部复用 `require_project`：

```python
def require_device(device_id: str, need: str = "read") -> dict:
    row = get_db().execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        raise ApiError("设备不存在", 404, "device_not_found")
    device = dict(row)
    require_project(device["project_id"], need)   # 越权同样抛 404
    return device

def require_diagram(diagram_id: str, need: str = "read") -> dict:
    row = get_db().execute("SELECT * FROM diagrams WHERE id=?", (diagram_id,)).fetchone()
    if not row:
        raise ApiError("图纸不存在", 404, "diagram_not_found")
    diagram = dict(row)
    if diagram["project_id"]:
        require_project(diagram["project_id"], need)
    else:
        _require_library_diagram(diagram, need)   # owner / 同团队 leader / admin
    return diagram

def visible_template_sql(user, alias="dt"):
    """模板可见域：成员/负责人看本团队；管理员看全部。"""
    if user["role"] == "admin":
        return "1=1", []
    return f"{alias}.team_id = ?", [user["team_id"]]


def require_template_read(template_id: str) -> dict:
    """模板详情：本团队可读；admin 可读全部；跨团队按不存在处理。"""
    row = get_db().execute(
        "SELECT * FROM device_templates WHERE id=?", (template_id,)
    ).fetchone()
    if not row:
        raise ApiError("模板不存在", 404, "template_not_found")
    user = current_user()
    if user["role"] != "admin" and row["team_id"] != user["team_id"]:
        raise ApiError("模板不存在", 404, "template_not_found")
    return dict(row)


def require_template_write(template_id: str | None = None) -> dict:
    """模板写权限：本团队所有成员/负责人；管理员只读；跨团队按不存在处理。"""
    user = current_user()
    if not user:
        raise ApiError("请先登录", 401, "not_authenticated")
    if user["role"] == "admin":
        raise ApiError("管理员对设备模板只读", 403, "forbidden")
    if not user["team_id"]:
        raise ApiError("当前账号没有团队", 403, "forbidden")
    if template_id:
        row = get_db().execute(
            "SELECT * FROM device_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not row or row["team_id"] != user["team_id"]:
            raise ApiError("模板不存在", 404, "template_not_found")
        return dict(row)
    return user
```

模板规则：

- 创建/导入：`team_id` 强制取当前用户的团队，忽略请求体里的 `team_id`；
- 读取：非管理员只能看到 `team_id = 自己团队` 的模板；管理员可传 `?team_id=` 筛选，响应带 `team_id` 与 `team_name`；
- 编辑/删除：只能操作本团队模板，跨团队一律 404（不泄露存在性）；
- 唯一性：同一团队内按 `(name, brand, model)` 唯一；CSV 重复判断按团队内 `(brand, model)`。

设备-节点关联必须做**双检**：

- `require_device(device_id, "write")`；
- `require_diagram(diagram_id, "write")`；
- 再校验 `device["project_id"] == diagram["project_id"]`，否则 422 `cross_project_link`。

### 4.4 各层落点

| 层 | 做法 |
|---|---|
| 页面路由（`app.py`） | `@login_required`；带对象的页面走 `require_project` / `require_diagram`，失败 **302 回首页** |
| API 蓝图 | 蓝图级 `before_request` 统一 `require_login()`；单对象路由再 `require_project` / `require_device` / `require_diagram` |
| 聚合查询（`api/views.py` 14 处） | 全部 `visible_project_sql()`；设备统计 JOIN 项目后再过滤 |
| AI 工具（`services_ai.py` 23 处） | 全部 `visible_project_sql()`；`_resolve_project()` 在解析后立刻校验 |
| 设备服务（`services_devices.py` 18 处） | 入口统一 `require_project`；`ensure_project()` 升级为带权限的解析 |
| 写入服务（`services.py`） | 创建时注入 `team_id`/`owner_user_id`；`log_activity` 带 `actor_user_id` |
| 设备模板 | 读接口用 `visible_template_sql()`；写接口统一 `require_template_write()`；管理员只读、可跨团队查看归属团队 |
| 共享与成员管理 | 共享接口校验「目标用户 ∈ 项目所在团队」；成员管理接口校验「目标用户 ∈ 操作者团队，且目标角色不是 leader/admin」 |
| 前端 | 只做「体验层」隐藏，**不得作为安全边界** |

### 4.5 页面对照

| 页面 | 登录 | 额外权限 |
|---|---|---|
| `/login` | 否 | — |
| `/healthz` | 否 | 返回体收敛为 `{"ok":true,"app":"TopoTash","time":...}`，**去掉数据库路径**（本地模式除外，见 9.10） |
| `/`、`/board`、`/diagrams` | 是 | 数据自动按可见域过滤 |
| `/device-templates` | 是 | 成员/负责人看本团队模板并可编辑；admin 看全部团队模板（含归属团队列/筛选）但隐藏编辑按钮 |
| `/projects/<id>` | 是 | `can_read`（owner / 被共享 / 本团队 leader / admin），否则 302 `/` |
| `/projects/<id>/diagrams/<did>` | 是 | 同上 + 图纸属于该项目 |
| `/diagrams/<did>`（库内图纸） | 是 | 图纸 owner 本人 / 同团队负责人 / 管理员，否则 302 `/diagrams` |
| `/team`（新增） | 是 | 所有登录用户可见名册；leader 额外获得本团队「建号 / 停用 / 重置密码」操作；admin 全部团队 |
| `/admin`（新增） | 是 | 仅 admin，否则 403 页 |
| `/static/**` | 否 | 静态资源不含业务数据；拓扑编辑器数据仍走已鉴权 API |

---

## 5. 认证与会话

### 5.1 登录流程

```
POST /api/auth/login  {email, password}
  ↓ 限流检查（ip + email 双维度）
  ↓ users 查询（email 唯一、不区分大小写）
  ↓ status='active' 校验
  ↓ scrypt 校验密码（werkzeug.security.check_password_hash）
  ↓ 成功：session["uid"]=id, session["epoch"]=users.session_epoch
  ↓ 失败：记一次 throttle，返回 401 "邮箱或密码不正确"（不区分哪个错）
返回 200 {user:{...}, csrf_token:"...", must_change_password:true}
```

- 登录成功后写 `last_login_at`，并清理该 `email` 维度的失败计数；
- `must_change_password=1` 时，前端强制跳转到改密界面（后端对所有业务接口返回 `403 password_change_required`，只放行 `/api/auth/*` 与静态资源）。

### 5.2 会话与 Cookie

- 使用 Flask 内置签名 Cookie（`SECRET_KEY` 必须来自环境变量，删除 `app.py:35` 的兜底默认值）。
- Cookie 配置：`HttpOnly=True`、`SameSite='Lax'`、`Secure=True`（仅 HTTPS 环境；宝塔必须开强制 HTTPS）、`PERMANENT_SESSION_LIFETIME=8h`。
- 每个请求的校验链：`session['uid']` → 查 `users` → `status='active'` → `session['epoch'] == users.session_epoch`。
  - 因为鉴权本来就要读用户，**epoch 校验不增加查询**；
  - 改密、禁用、管理员「强制下线」都只需 `session_epoch += 1`，立即全端失效。
- 不建会话表：因此无法提供「登录设备列表」与「按设备下线」。这是为低并发场景做的明确取舍。

### 5.3 CSRF

Cookie 认证后必须防 CSRF：

1. 主防线：`SameSite=Lax`；
2. 次防线：双提交 token —— 登录时下发可读 Cookie `tt_csrf`（随机 32 hex），前端每个写请求带 `X-TT-CSRF` 头，服务端比对；
3. 第三层：现有 `app.py:51` 已要求写请求必须是 JSON 对象，表单跨站提交天然无法伪造 `application/json`；
4. **multipart 例外必须补**：设备模板 CSV 导入使用 `multipart/form-data`，当前 `validate_api_body` 会跳过 JSON 校验，因此 CSRF 中间件必须对 **包括 multipart 在内的所有写方法** 校验 `X-TT-CSRF`。

实现：`api` 蓝图 `before_request` 中对 `POST/PUT/PATCH/DELETE` 校验第 2 层，`/api/auth/login` 豁免。

### 5.4 密码与限流

| 项 | 规则 |
|---|---|
| 哈希 | `werkzeug.security.generate_password_hash`（scrypt，Flask 自带，零新依赖） |
| 强度 | 长度 ≥ 10，且不是纯数字；不强制大小写/符号（可用性优先） |
| 初始密码 | 管理员创建账号时指定；`must_change_password=1` 强制首登修改 |
| 重置 | 管理员重置为临时密码 + `must_change_password=1` + `session_epoch += 1` |
| 限流 | 同一 `ip` 或同一 `email`：15 分钟内失败 5 次 → 锁定 15 分钟（`login_throttle` 表）；锁定期返回 429 与剩余秒数 |
| 改密 | 需校验旧密码；成功后 `session_epoch += 1` 并重新签发当前会话 |

### 5.5 账号生命周期

| 动作 | 权限 | 影响 |
|---|---|---|
| 创建用户 | admin（任意角色）<br>leader（**仅本团队、仅 member**） | 生成 `must_change_password=1`；admin 创建时必须指定 role 与 team（admin 除外）；leader 创建的账号团队与角色被服务端强制为「本团队 + member」 |
| 禁用用户 | admin（全部）<br>leader（**仅本团队 member**） | `status='disabled'` + `session_epoch += 1`；其项目保留，仍归其名下（管理员/负责人可见） |
| 删除用户 | admin | **禁止硬删除**：改为禁用。避免 `owner_user_id` 悬空导致数据失去归属 |
| 更换团队 | admin | 事务内**清除该用户在所有项目上的 `project_members` 记录**；其名下项目默认**不随迁**，由 admin 逐个转移 |
| 提升为 leader | admin | 立即获得本团队全部项目可见性（注意：这是权限放大，UI 要有确认） |
| 重置密码 | admin（全部）<br>leader（**仅本团队 member**） | 生成临时密码 + `must_change_password=1` + `session_epoch += 1` |

### 5.6 本地免登录模式（D9）

本地 Windows 启动器必须保留「双击即用」：

- `start_topotash.py` 在导入 `app` 前设置 `TOPOTASH_LOCAL_MODE=1`；
- `create_app()` 检测到本地模式时：
  - 跳过登录校验，注入内置的 `local-admin` 身份（`role='admin'`，`team_id=NULL`）；
  - `/api/auth/me` 返回本地用户与全部 `can` 标记；
  - 不启用 CSRF（现有前端无需改动）；
  - `/healthz` 保留 `database` 字段，供启动器区分实例；
  - 页面不显示登录/团队/管理入口，侧栏底部显示「本地模式」。
- 安全约束：
  - 本地模式只在 `start_topotash.py` 中开启，且服务只绑定 `127.0.0.1`；
  - 若同时检测到 `TOPOTASH_DEPLOY=production`，启动直接报错退出；
  - 部署清单明确检查「生产环境不得设置 `TOPOTASH_LOCAL_MODE`」。
- 线上环境完全不使用本地模式；认证逻辑只有一条生产路径。

---

## 6. API 契约

### 6.1 新增接口

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 公开 | 登录，返回用户 + csrf token |
| POST | `/api/auth/logout` | 登录 | 清理会话 |
| GET | `/api/auth/me` | 登录 | 当前用户、角色、团队、权限标记 |
| POST | `/api/auth/password` | 登录 | 修改自己的密码（需旧密码） |
| GET | `/api/team/members` | 登录 | 本团队名册（含角色、状态、项目数；member 只读） |
| POST | `/api/team/members` | leader / admin | 在本团队创建 **member** 账号（**不能**指定 `leader`/`admin`） |
| PATCH | `/api/team/members/<id>` | leader / admin | 改名 / 停用启用；**不能**改角色、不能动其他团队、不能动 leader/admin |
| POST | `/api/team/members/<id>/reset-password` | leader / admin | 重置为临时密码 + `must_change_password=1` + 强制下线 |
| GET | `/api/projects/<id>/shares` | `can_read` | 该项目的共享列表 |
| POST | `/api/projects/<id>/shares` | `can_manage` | 新增或更新共享 `{user_id, access:"view"\|"edit"}` |
| DELETE | `/api/projects/<id>/shares/<user_id>` | `can_manage` | 取消共享 |
| GET | `/api/admin/users` | admin | 全量账号列表（支持 `?q=`、`?team_id=`） |
| POST | `/api/admin/users` | admin | 创建任意角色账号（含 leader） |
| PATCH | `/api/admin/users/<id>` | admin | 改姓名/角色/团队/状态 |
| POST | `/api/admin/users/<id>/reset-password` | admin | 重置为临时密码 |
| GET | `/api/admin/teams` | admin | 团队列表（含人数、项目数） |
| POST | `/api/admin/teams` | admin | 新建团队 |
| PATCH | `/api/admin/teams/<id>` | admin | 改名/备注 |
| DELETE | `/api/admin/teams/<id>` | admin | 仅当团队下无用户且无项目 |

共享接口的约束（服务端强制，前端也做提示）：

- 目标用户必须**存在、处于 active、且与项目属于同一团队**，否则 422 `share_target_invalid`；
- 目标用户不能是项目 owner 本人；
- 目标用户不能是本团队 leader（权限已覆盖）；
- 被共享用户被移出/更换团队时，迁移逻辑须删除其相关 `project_members`（INV-8）。

`POST /api/auth/login` 请求/响应示例：

```json
// 请求
{ "email": "zhang@example.com", "password": "**********" }

// 200
{
  "user": { "id": "u_ab12cd34ef56", "email": "zhang@example.com",
            "display_name": "张三", "role": "leader", "team_id": "t_x1", "team_name": "华东售前" },
  "csrf_token": "7f3c…",
  "must_change_password": false
}

// 401
{ "error": { "code": "bad_credentials", "message": "邮箱或密码不正确" } }

// 429
{ "error": { "code": "too_many_attempts", "message": "尝试次数过多，请 12 分钟后重试" } }
```

`GET /api/auth/me` 响应中额外给出前端需要的粗粒度标记：

```json
{ "user": {...}, "can": { "create_project": true, "manage_users": false,
                          "manage_teams": false, "write_ai_config": false,
                          "edit_team_templates": true, "view_all_templates": false } }
```

### 6.2 现有 65 个接口的权限标注

#### `projects`（9）

| 接口 | 权限 |
|---|---|
| `GET /api/projects` | 登录 + 可见域过滤（`visible_project_sql`，含被共享项目） |
| `POST /api/projects` | 登录；owner=自己，team=自己团队（admin 必须传 `team_id`） |
| `GET /api/projects/<id>` | `require_project(read)` |
| `PATCH /api/projects/<id>` | 普通字段 `require_project(write)`；**改 `owner_user_id` 需 `can_manage` 且新 owner 同团队**；**改 `team_id` 仅 admin** |
| `DELETE /api/projects/<id>` | **`require_project(manage)`**——被共享的 edit 用户不能删项目 |
| `GET /api/projects/<id>/todo-state` | `require_project(read)` |
| `PUT /api/projects/<id>/todo-state` | `require_project(write)` |
| `GET /api/projects/<id>/devices/summary` | `require_project(read)` |
| `GET /api/projects/<id>/devices/export.csv` | `require_project(read)`；导出含单价，按项目读权限控制 |

#### `tasks`（11）

全部先由 `task_id → project_id` 反查再 `require_project`。

| 接口 | 权限 |
|---|---|
| `GET /api/tasks` | 登录 + 可见域过滤（JOIN projects） |
| `POST /api/tasks` | `require_project(write)`（body 里的 `project_id`） |
| `GET/PATCH/DELETE /api/tasks/<id>` | `require_project(read/write/write)` |
| 子任务 3 个、标签 1 个 | 同上（写） |
| `POST/DELETE /api/tasks/<id>/diagrams` | 任务与图纸**双方**都要可写（跨项目关联必须双检） |

#### `diagrams`（16）

| 接口 | 权限 |
|---|---|
| `GET /api/diagrams` | 登录 + 可见域：绑定项目的图纸按「可见项目集合」过滤（含被共享），库内图纸按 `owner_user_id`（leader 按 owner 的团队） |
| `POST /api/diagrams` | 登录；绑定到项目时 `require_project(write)`；库内时 owner=自己 |
| `POST /api/diagrams/import` | 同上 |
| `POST /api/diagrams/<id>/duplicate` | 源图纸可读 + 目标项目可写 |
| `GET /api/diagrams/<id>` | 可读（`require_diagram`） |
| `PATCH /api/diagrams/<id>` | 可写；允许改 `project_id` 时需同时对目标项目有写权限 |
| `DELETE /api/diagrams/<id>` | 可写 |
| `GET/PUT /api/diagrams/<id>/content` | 可读 / 可写（`PUT` 保留 `version` 冲突检测） |
| `GET /api/diagrams/<id>/nodes` | 可读 |
| `PATCH /api/diagrams/<id>/nodes/<key>` | 可写 |
| `POST /api/diagrams/<id>/nodes/<key>/followup` | 可写 |
| `POST/DELETE /api/diagrams/<id>/nodes/<key>/links` | 可写（任务与图纸双方项目都要可写） |
| `POST/DELETE /api/diagrams/<id>/nodes/<key>/devices` | 可写；设备与图纸必须同项目 |

#### `devices`（7，本次新增权限面）

| 接口 | 权限 |
|---|---|
| `GET /api/devices?project_id=` | `require_project(read)`；`project_id` 必填 |
| `POST /api/devices` | `require_project(write)`（body 的 `project_id`） |
| `GET /api/devices/<id>` | `require_device(read)` |
| `PATCH /api/devices/<id>` | `require_device(write)`；`links` 全量替换时逐条校验同项目 |
| `DELETE /api/devices/<id>` | `require_device(write)` |
| `POST /api/devices/<id>/nodes` | `require_device(write)` + `require_diagram(write)` + 同项目 |
| `DELETE /api/devices/<id>/nodes/<did>/<key>` | 同上 |

#### `device-templates`（7，按 D8 团队共享）

| 接口 | 权限 |
|---|---|
| `GET /api/device-templates` | 登录；成员/负责人只能看到本团队模板；admin 可看全部，支持 `?team_id=`，响应含 `team_id` / `team_name` |
| `GET /api/device-templates/<id>` | 登录；本团队模板可读；跨团队 404；admin 可读全部 |
| `GET /api/device-templates/sample.csv` | 登录 |
| `POST /api/device-templates` | 本团队**成员/负责人**；`team_id` 强制取当前用户团队；admin 403（只读） |
| `PATCH /api/device-templates/<id>` | 本团队**成员/负责人**；跨团队 404；admin 403 |
| `DELETE /api/device-templates/<id>` | 本团队**成员/负责人**；跨团队 404；admin 403 |
| `POST /api/device-templates/import` | 本团队**成员/负责人**（含 multipart 与 `dry_run`）；重复判断按团队内 `(brand, model)`；admin 403 |

> 列表接口返回的分类计数、品牌列表、总数也必须按可见域过滤：成员/负责人只统计本团队；admin 统计全部（若传 `?team_id=` 则统计该团队）。

#### `views`（4）

`GET /api/views/overview|stage-board|links|search` —— 全部登录 + 可见域过滤。这是**最容易被忽略的泄露面**：

- `overview` 现在 `SELECT * FROM projects`（`api/views.py:26`）、`SELECT * FROM tasks`（`api/views.py:29`）；
- `stage-board` 现在查全部任务与项目（`api/views.py:119`、`api/views.py:135`）；
- `links` 现在查全部图纸与任务关联（`api/views.py:158`）；
- `search` 现在搜全部任务（`api/views.py:192`）。

必须全部改成 `visible_project_sql()`，并且设备统计要以项目为入口过滤。

#### `ai`（11）

| 接口 | 权限 |
|---|---|
| `GET /api/ai/config` | 登录（响应已脱敏，可全员读） |
| `PUT /api/ai/config` | **admin** |
| `POST /api/ai/test` | **admin** |
| `GET/POST /api/ai/conversations` | 登录，仅自己的会话 |
| `GET/DELETE /api/ai/conversations/<id>` | 仅会话 owner，否则 404 |
| `POST /api/ai/chat` | 登录；会话 owner |
| `POST /api/ai/topology` | 登录（无项目上下文，纯模型代理） |
| `POST /api/ai/actions/<id>/confirm` | 会话 owner + **目标项目写权限**（二次校验） |
| `POST /api/ai/actions/<id>/cancel` | 会话 owner |

### 6.3 错误码约定

| HTTP | code | 场景 |
|---|---|---|
| 401 | `not_authenticated` | 未登录访问 API |
| 401 | `bad_credentials` | 登录失败 |
| 403 | `forbidden` | 调用管理员专属接口 |
| 403 | `role_escalation_forbidden` | leader 试图创建/提升 leader 或 admin，或操作非本团队用户 |
| 403 | `password_change_required` | 首登/重置后未改密 |
| 404 | `project_not_found` / `diagram_not_found` / `device_not_found` / `conversation_not_found` / `template_not_found` | 不存在**或**无权限（刻意不区分；跨团队模板同样返回 404） |
| 409 | `template_duplicate` | 同团队内已存在相同品牌+型号的模板 |
| 422 | `share_target_invalid` | 共享目标不在同团队 / 已停用 / 是 owner 本人 / 是 leader |
| 422 | `cross_project_link` | 设备与图纸不属于同一项目 |
| 429 | `too_many_attempts` | 登录限流 |

前端约定：`401 → 跳 /login?next=…`；`403 password_change_required → 跳 /password`；`404 → toast「对象不存在或无权访问」`。

---

## 7. 前端改造

| 文件 | 改动 |
|---|---|
| `templates/login.html`（新） | 登录表单、错误提示、限流剩余时间 |
| `templates/password.html`（新） | 强制改密页 |
| `templates/team.html`（新） | 团队页：名册；leader 额外有「新建成员」「停用/启用」「重置密码」；admin 可切换团队 |
| `templates/admin.html`（新） | 管理后台：团队 CRUD、全量账号 CRUD、角色调整 |
| `templates/base.html` | `side-foot` 改为真实用户 + 下拉菜单（改密/退出/团队/管理）；`nav` 增加「团队」；admin 增加「管理」；注入 `window.TT_ME`、`window.TT_CAN`；本地模式显示「本地模式」 |
| `static/js/api.js` | 统一附带 `X-TT-CSRF`；拦截 401/403 做跳转；`credentials:'same-origin'`；本地模式跳过 CSRF |
| `static/js/shell.js` | 渲染用户菜单；退出登录；搜索无结果空态 |
| `static/js/dashboard.js`、`board.js`、`diagrams.js` | 按 `TT_CAN` 与资源归属隐藏新建/删除/绑定按钮 |
| `static/js/project.js` | 项目头新增「共享」按钮（`can_manage` 才显示）；被共享的 edit 用户隐藏「删除项目」 |
| `static/js/tasks.js` | 按 `TT_CAN` 隐藏删除/转移/绑定按钮 |
| `static/js/devices.js` | 只读用户隐藏新增/编辑/删除/关联；导出 CSV 仍按项目读权限开放 |
| `static/js/device-templates.js` | 成员/负责人显示本团队模板与新增/编辑/删除/导入；admin 显示全部团队模板、归属团队列与团队筛选，但隐藏所有写按钮 |
| `static/js/editor.js` + `static/apps/topology/*` | 拓扑桥接接口失败时提示「无权限」；不把权限判断放进 iframe，服务端仍是唯一边界 |
| `static/js/share.js`（新） | 共享弹窗：团队成员搜索、view/edit 切换、撤销共享、显示授权人/时间 |
| `static/js/team.js`（新） | 名册渲染、新建成员（随机初始密码一次性展示）、重置密码、停用/启用 |
| `static/js/admin.js`（新） | 账号/团队 CRUD、角色调整（含提升 leader 的二次确认） |
| 全局 | 页面加载先 `GET /api/auth/me`，失败即 `location='/login'`；本地模式直接使用返回的本地用户 |

新增页面/控件清单（按当前 UI）：

- 顶部导航：在「项目总览 / 阶段看板 / 拓扑图库 / 设备模板」基础上增加「团队」，admin 增加「管理」；
- 项目工作台五个标签：概览 / 任务 / 拓扑图 / 关联视图 / 设备清单——设备清单的写操作按项目写权限控制；
- 拓扑编辑器属性面板的「TopoTash 设备」区块：无写权限时只展示已关联设备，隐藏「关联 / 新建」；
- 设备模板页：成员/负责人可维护本团队模板；管理员看到全部团队的模板与「归属团队」列（可按团队筛选），但没有新增、编辑、删除、CSV 导入按钮；
- 设备弹窗与拓扑属性面板的模板下拉：只加载当前用户可见的模板（成员=本团队，admin=全部，选中后显示归属团队）。

---

## 8. AI 助手的权限边界

### 8.1 数据面

`services_ai.py` 有 23 处查询参与权限，重点是：

| 位置 | 现状 | 要求 |
|---|---|---|
| `_resolve_project()`（`services_ai.py:761`） | 按名称/ID 解析**任意**项目 | 解析后立即 `can_read` 校验，否则返回「找不到该名称的项目」 |
| `_tool_list_projects()` | 列出全部项目 | 仅可见域内 |
| `_tool_search()` | 全库搜索 | 仅可见域内（任务要 JOIN 项目过滤） |
| `_tool_portfolio_summary()` | 统计全部 | 仅可见域内 |
| `apply_action()` | 草稿直接写库 | 执行前**重新**校验目标项目写权限 |

注意：AI 的「找不到」提示必须是**中性**的（不能因为权限拒绝而暴露「该项目存在但你看不到」）。当前 AI 工具不涉及设备/模板，暂不扩展；如果后续增加设备工具，必须沿用 `require_project`。

### 8.2 配置面

保持全局唯一（D4）：

- `GET /api/ai/config` 全员可读，但只返回 `api_key_hint`；
- `PUT /api/ai/config`、`POST /api/ai/test` 仅 admin；
- 前端 AI 设置入口对非 admin 只读展示（显示当前模型与「由管理员配置」提示）。

### 8.3 静态资源

`/static/apps/topology/index.html` 是拓扑编辑器单页，可由 Nginx 直接托管（见 9.5），**不经过 Flask 鉴权**。这是可接受的，因为：

1. 该 HTML 不含任何业务数据，数据全部通过 `/api/diagrams/**` 获取，而这些接口已鉴权；
2. 需确保 `static/` 下永远不出现数据文件（当前只有代码、图标与字体）。

若后续需要更严格，可给 iframe 换成一个 `@login_required` 的 Flask 路由来返回该文件（代价是静态缓存失效），列为可选加固项。

---

## 9. 部署方案（公有云 + 宝塔）

### 9.1 拓扑

```
客户端 ──HTTPS(443)──> Nginx(宝塔站点) ──proxy──> Gunicorn(127.0.0.1:8000, 2×4)
                            │                          │
                            ├─ /static/ 直接由 Nginx 返回
                            │                          └── SQLite: /www/wwwroot/topotash/data/topotash.db (WAL)
                            └─ 证书：Let's Encrypt（宝塔自动续期）
                                                 └── 备份：每日 03:00 → /www/backup/topotash/
```

并发结论（D2）：2 个 worker × 4 线程，SQLite WAL + `busy_timeout`，对「≤10 人、以读为主」的场景绰绰有余。**不要**开多实例或负载均衡——SQLite 单写者模型下多实例只会互相等锁。

### 9.2 环境准备

| 项 | 建议值 |
|---|---|
| 系统 | Ubuntu 22.04 / Debian 12（宝塔支持良好） |
| 规格 | 2 核 4 G、40 G SSD（含备份余量） |
| Python | 3.11 或 3.12（**不要用 3.15 等过新版本**） |
| 目录 | 代码 `/www/wwwroot/topotash`；数据 `/www/wwwroot/topotash/data`；备份 `/www/backup/topotash` |
| 运行用户 | `www` |
| 端口 | 对外 80/443；Gunicorn 只监听 `127.0.0.1:8000` |

### 9.3 环境变量（宝塔 Python 项目管理器「环境变量」中配置）

| 变量 | 示例 | 说明 |
|---|---|---|
| `TOPOTASH_SECRET` | 64 位随机串 | **必填**，删除代码兜底后不设置将无法启动 |
| `TOPOTASH_DB` | `/www/wwwroot/topotash/data/topotash.db` | 数据与代码分离 |
| `TOPOTASH_AUTO_MIGRATE` | `0` | 生产关闭启动自动迁移 |
| `TOPOTASH_ADMIN_EMAIL` | `admin@example.com` | 仅首次迁移使用 |
| `TOPOTASH_ADMIN_PASSWORD` | 临时强密码 | 仅首次迁移使用，**迁移后立即删除** |
| `TOPOTASH_COOKIE_SECURE` | `1` | HTTPS 下强制 Secure Cookie |
| `TOPOTASH_ICP` | `苏ICP备XXXXXXXX号` | 页脚备案号 |
| `TOPOTASH_DEPLOY` | `production` | 与本地模式互斥，防止误开免登录 |
| `TOPOTASH_LOCAL_MODE` | **不设置** | 生产环境绝不允许设置 |

### 9.4 部署步骤

1. 宝塔安装：Nginx、Let's Encrypt、`Python 项目管理器`。
2. 用 Python 项目管理器安装 Python 3.11，创建项目：
   - 路径 `/www/wwwroot/topotash`（`git clone` 或上传代码）
   - 启动方式 `gunicorn`，启动文件 `wsgi.py`，启动命令
     `gunicorn -w 2 -k gthread --threads 4 -b 127.0.0.1:8000 --timeout 300 wsgi:app`
   - 依赖安装：`pip install -r requirements-prod.txt`
   - 运行用户 `www`
3. 创建数据目录并授权：
   ```bash
   mkdir -p /www/wwwroot/topotash/data /www/backup/topotash
   chown -R www:www /www/wwwroot/topotash/data /www/backup/topotash
   chmod 750 /www/wwwroot/topotash/data
   ```
4. 配置环境变量（9.3），然后**手工执行一次初始化与迁移**：
   ```bash
   cd /www/wwwroot/topotash
   /path/to/venv/bin/python -m flask --app app init-db
   # 首次迁移会创建默认团队与管理员；记下打印的初始密码
   ```
   迁移完成后从环境变量中删除 `TOPOTASH_ADMIN_PASSWORD`，并确认 `TOPOTASH_AUTO_MIGRATE=0`。
   随后在管理后台为「默认团队」创建 leader 或 member：存量设备模板归默认团队，管理员对模板只读，必须有团队账号才能继续维护。
5. 添加站点（绑定域名），网站设置 → 反向代理 → 目标 `http://127.0.0.1:8000`。
6. 网站设置 → SSL → Let's Encrypt 申请 → 开启**强制 HTTPS**。
7. Nginx 追加配置（网站 → 配置文件），见 9.5。
8. 防火墙：只放行 80/443 与宝塔面板端口；8000 不对外（`ss -lntp` 确认只监听 127.0.0.1）。
9. 计划任务：每日 03:00 自动备份，每月一次恢复演练（见 9.6）。

> 若站点开启了「防跨站攻击（open_basedir）」，需把 `data/` 加入允许路径，或把数据库放在站点根目录内并靠 9.5 的 `deny all` 保护。

### 9.5 Nginx 配置

```nginx
client_max_body_size 32m;                 # 画布 JSON / CSV 导入上限
add_header Strict-Transport-Security "max-age=31536000" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;

location ^~ /data/ { deny all; }          # 数据库目录绝不可被 Web 访问
location ^~ /tools/ { deny all; }
location ~* /\.(git|env) { deny all; }
location ~* \.(db|sqlite|db-wal|db-shm)$ { deny all; }

location /static/ {
    alias /www/wwwroot/topotash/static/;
    expires 7d;
    access_log off;
}

# AI 流式接口：关闭缓冲、延长超时
location /api/ai/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}
```

要点：

- `/api/ai/topology` 是 `text/event-stream`，后端已带 `X-Accel-Buffering: no`，Nginx 仍建议 `proxy_buffering off` 与 300s 超时；
- 32MB 上传要与 Flask 的 `MAX_CONTENT_LENGTH` 对齐；
- 设备模板 CSV 导入是 `multipart/form-data`，不要被反代或 WAF 拦截；
- 若把 `/static/` 交给 Nginx，确保 `/static/apps/topology/` 与 `/static/apps/tasks/` 的 MIME 正常；否则可去掉该 location，让 Flask 托管。

### 9.6 备份与恢复

新增 `tools/backup_db.py`（当前文档引用但文件不存在），用 SQLite 备份 API，WAL 安全：

```python
"""按日备份 SQLite 数据库，保留 14 天。"""
import sqlite3, sys
from datetime import datetime
from pathlib import Path

src_path, dest_dir = Path(sys.argv[1]), Path(sys.argv[2])
dest_dir.mkdir(parents=True, exist_ok=True)
target = dest_dir / f"topotash-{datetime.now():%Y%m%d-%H%M%S}.db"
with sqlite3.connect(src_path) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
for old in sorted(dest_dir.glob("topotash-*.db"))[:-14]:
    old.unlink()
print(target)
```

宝塔计划任务（Shell 脚本，每日 03:00）：

```bash
cd /www/wwwroot/topotash && /usr/bin/python3 tools/backup_db.py \
  /www/wwwroot/topotash/data/topotash.db /www/backup/topotash
```

恢复演练（每月一次，在测试环境）：

```bash
# 停项目
cp /www/backup/topotash/topotash-YYYYmmdd-HHMMSS.db /www/wwwroot/topotash/data/topotash.db
rm -f /www/wwwroot/topotash/data/topotash.db-wal /www/wwwroot/topotash/data/topotash.db-shm
chown www:www /www/wwwroot/topotash/data/topotash.db
sqlite3 /www/wwwroot/topotash/data/topotash.db "PRAGMA integrity_check;"
```

### 9.7 升级流程

```bash
# 1) 备份
python3 tools/backup_db.py data/topotash.db /www/backup/topotash
# 2) 停服务（宝塔面板 → Python 项目 → 停止）
# 3) 拉代码
git pull --ff-only origin main
# 4) 依赖
pip install -r requirements-prod.txt
# 5) 迁移（幂等）
flask --app app init-db
# 6) 启动并验证
curl -fsS https://你的域名/healthz
```

### 9.8 安全加固清单

- [ ] `TOPOTASH_SECRET` 已设置且为随机值；代码里的兜底默认值已删除
- [ ] 生产 `TOPOTASH_AUTO_MIGRATE=0`、`TOPOTASH_DEPLOY=production`
- [ ] `TOPOTASH_LOCAL_MODE` **未设置**
- [ ] `/healthz` 不再返回数据库路径（本地模式除外）
- [ ] 500 错误不再把异常原文返回给浏览器（生产只返回通用提示）
- [ ] `/data/`、`/tools/`、`.git`、`.env`、`*.db` 均 403
- [ ] 强制 HTTPS + HSTS；Cookie `Secure`+`HttpOnly`+`SameSite=Lax`
- [ ] 登录限流生效（连续 6 次错误应返回 429）
- [ ] CSRF 对 JSON 与 multipart 写请求都生效
- [ ] 管理员初始密码已修改，`must_change_password` 已清零
- [ ] 数据库文件权限 750、属主 `www`，不在 Web 可读路径
- [ ] 每日备份存在且可恢复（做过一次恢复演练）
- [ ] 页脚展示备案号并链接工信部（`TOPOTASH_ICP` 已配置）
- [ ] 宝塔面板本身：改默认入口、开两步验证、限制 IP
- [ ] 清理仓库根目录无关文件（当前有一个未跟踪的 `CON`）

### 9.9 域名与备案（已确认有备案域名）

| 事项 | 做法 |
|---|---|
| 解析 | 域名添加 A 记录指向服务器公网 IP；宝塔站点绑定该域名 |
| 证书 | 宝塔 SSL → Let's Encrypt（HTTP-01 校验需要 80 端口可达，勿被 CDN/跳转拦截）；开启强制 HTTPS 后 HSTS 生效 |
| 备案号展示 | 工信部要求：页面底部展示备案号并链接 `https://beian.miit.gov.cn/`。在 `templates/base.html` 与 `login.html` 页脚各加一处，备案号由 `TOPOTASH_ICP` 注入 |
| 备案一致性 | 备案主体与网站实际内容需一致；换服务器（同主体）无需重新备案，但需保证接入商信息与实际一致，必要时做「接入备案」 |
| Cookie 域 | 使用一级域名，勿用带端口的临时地址 |
| 健康检查 | 用 `https://域名/healthz` 做监控探针（不要用 IP，避免证书告警） |

### 9.10 本地模式与线上模式的分界

| 项 | 本地模式 | 线上模式 |
|---|---|---|
| 入口 | `start_topotash.py` / `首次启动.bat` | `gunicorn wsgi:app` |
| 监听 | `127.0.0.1` | `127.0.0.1:8000` + Nginx |
| 认证 | 免登录，内置 local-admin | 强制登录 |
| CSRF | 关闭 | 开启 |
| `SECRET_KEY` | 首次运行生成 `.topotash_secret`（gitignored） | `TOPOTASH_SECRET` 必填 |
| 数据 | 项目目录 `topotash.db` | `/www/wwwroot/topotash/data/topotash.db` |
| 迁移 | 启动时自动执行 | 手工 `flask init-db` |
| `/healthz` | 含 `database` 字段 | 不含 `database` 字段 |

---

## 10. 测试计划

### 10.1 基线改造

现有 172 个 `unittest` 用例（`tests/support.py` 提供独立临时库）全部保持通过。**必须先改测试基座**：

- `ApiTestCase.setUp()` 在创建 app 后，自动创建「测试团队 + 管理员」并登录，使既有用例继续以管理员身份运行（行为等价于当前全可见）；
- 页面路由测试同样带登录会话；
- 新增一组「未登录 client」用例，专门验证 401 / 302；
- 本地模式单独用 `create_app({"TESTING": True, "LOCAL_MODE": True})` 验证，不影响生产认证用例。

> 如果直接把认证打开而不改测试基座，172 个用例会大面积 401，无法判断是回归还是预期变化。

### 10.2 新增测试文件

| 文件 | 覆盖 |
|---|---|
| `tests/test_auth.py` | 登录成功/失败、限流锁定、登出、改密、`must_change_password` 拦截、session_epoch 失效、本地模式免登录 |
| `tests/test_access.py` | `can_read`/`can_write`/`can_manage`/`visible_project_sql` 的纯逻辑矩阵；`require_project` 抛 404 |
| `tests/test_sharing.py` | 共享授予/改档/撤销；view 只读、edit 可写；被共享 edit 不能删项目/管共享；跨团队共享被拒 |
| `tests/test_team_api.py` | leader 建号（只能建 member）、停用、重置密码；leader 不能动其他团队、不能动 leader/admin；member 调管理接口 403 |
| `tests/test_tenant_isolation.py` | 每个聚合接口（overview、stage-board、links、search、projects、tasks、diagrams、devices、AI 工具）不出现对方未被共享的数据 |
| `tests/test_admin_api.py` | 账号 CRUD、重置密码、团队 CRUD、非 admin 调用返回 403 |
| `tests/test_migration_v6.py` | v5 库迁移到 v6 后数据量不变（含 devices/device_node_links/device_templates）、归属正确、`foreign_key_check` 通过、重复迁移幂等 |
| `tests/test_devices_access.py` | 设备读/写/删随项目权限；跨项目设备-节点关联 422；CSV 导出按项目读权限 |
| `tests/test_device_templates_scope.py` | 模板按团队隔离；本团队成员/负责人可增删改/导入；跨团队读 404、写 404；admin 全局只读并返回团队信息；唯一键按团队生效；CSV 重复判断按团队内 `(brand, model)` |

### 10.3 关键用例

| 编号 | 断言 |
|---|---|
| TC-01 | 成员 A 看不到成员 B 的项目（列表、看板、总览、搜索、AI 列表均无） |
| TC-02 | 成员 A 直接 `GET /api/projects/<B的项目>` 返回 404 |
| TC-03 | 成员 A `PATCH/DELETE` 他人项目返回 404，且数据库未变更 |
| TC-04 | 负责人能看到并编辑本团队全部项目，但不能看到其他团队 |
| TC-05 | 负责人 `PATCH` 他人项目为 200（写权限成立） |
| TC-06 | 管理员能跨团队移动项目；负责人不能（403/404） |
| TC-07 | 未登录访问任意 API 返回 401；访问页面 302 到 `/login` |
| TC-08 | 非 admin 调用 `PUT /api/ai/config` 返回 403；`GET` 返回脱敏 |
| TC-09 | 新建项目必带 `team_id`/`owner_user_id`（INV-2） |
| TC-10 | 成员 A 的 AI 会话列表不含 B 的会话；`DELETE` B 的会话返回 404 |
| TC-11 | AI 草稿确认时，若目标项目已被转移给他人，确认返回 404 且不写库 |
| TC-12 | 删除任务/图纸后，节点跟进、设备关联与关联清理行为与现状一致（防回归） |
| TC-13 | 迁移后 172 个旧用例仍全绿（行为等价性） |
| TC-14 | 连续 5 次错误密码后第 6 次返回 429，且正确密码在锁定期内也不放行 |
| TC-15 | 共享 `view`：B 能看到 A 的项目详情，但 `PATCH` 返回 404，且库内数据未变 |
| TC-16 | 共享 `edit`：B 能改任务、画布、设备，但 `DELETE /api/projects/<id>` 返回 404、共享接口返回 403 |
| TC-17 | 撤销共享后，B 的详情立刻 404，列表/看板/搜索中也不再出现 |
| TC-18 | 跨团队共享返回 422；共享给 leader 本人或 owner 本人同样被拒 |
| TC-19 | leader 创建成员成功；尝试创建 `leader` / `admin` 返回 403 `role_escalation_forbidden` |
| TC-20 | leader 停用本团队成员后，该成员已有会话立即失效 |
| TC-21 | 项目 owner 转移给同团队他人后，原 owner 立即 404，新 owner 可写，共享记录保留 |
| TC-22 | 成员 A 读/写他人项目设备返回 404；被共享 `view` 可读设备但不能改 |
| TC-23 | 设备与图纸跨项目关联返回 422 `cross_project_link`，且不写库 |
| TC-24 | 团队成员/负责人可新增、编辑、删除本团队模板并 CSV 导入；其他团队看不到该模板（列表不含、详情 404、写 404）；admin 对模板写接口返回 403 |
| TC-25 | 设备 CSV 导出对无项目读权限的用户返回 404 |
| TC-26 | v5 → v6 迁移后 devices / device_node_links / device_templates 数量不变，模板 `team_id` 全部回填为默认团队，外键检查通过 |
| TC-27 | 本地模式不登录可访问页面；生产模式未登录返回 401/302；`TOPOTASH_LOCAL_MODE=1` + `TOPOTASH_DEPLOY=production` 启动报错 |
| TC-28 | 管理员 `GET /api/device-templates` 能看到两个团队的模板，响应含 `team_id` / `team_name`，并可用 `?team_id=` 筛选；成员只能看到本团队 |
| TC-29 | 两个团队可以各自创建相同 `(brand, model)` 的模板；同团队重复创建返回 409 `template_duplicate`；CSV 导入的重复判断只在本团队内生效 |
| TC-30 | 管理员创建模板返回 403；成员创建的模板 `team_id` 等于创建者团队，忽略请求体中伪造的 `team_id` |

### 10.4 前端验证

- 三种角色各走一遍：登录 → 总览 → 项目 → 任务 → 拓扑图 → 设备清单 → 设备模板 → 登出；
- **共享闭环**：A 共享给 B（查看）→ B 能看到、能开画布、能看设备但改不动；改成（编辑）→ B 能改任务、画布与设备；A 撤销 → B 刷新后项目消失；
- **leader 闭环**：leader 新建成员 → 新成员首登被强制改密 → leader 把某项目改派给该成员 → 原 owner 打开该项目回首页；
- **模板权限**：普通成员/负责人能看并维护本团队模板、能在设备弹窗套用；切到其他团队账号看不到本团队模板；管理员能看到两个团队的模板与归属团队列，但没有新增/编辑/导入按钮；
- 直接输 URL 访问他人项目/设备/图纸 → 回首页；
- 断网/会话过期 → 401 → 自动跳登录，登录后回到原页面（`next` 参数）；
- 本地模式双击 `首次启动.bat` → 不出现登录页，功能与当前一致；
- 浏览器控制台无 403/404 噪声（说明 UI 隐藏逻辑到位）。

---

## 11. 实施计划

> v1.1 的 P0「先部署无权限版本」**废弃**。在认证完成前，不得把应用直接暴露到公网。

| 阶段 | 内容 | 产出 | 人日 |
|---|---|---|---|
| P0 | 生产基线：`wsgi.py`、`requirements-prod.txt`、gunicorn、环境变量守卫、`/healthz` 收敛、500 错误脱敏、`tools/backup_db.py`、Nginx 配置 | 可部署但不对外开放的骨架 | 2 |
| P1 | schema v6 + 迁移 + 引导管理员 + 回填（含设备/模板校验、模板 `team_id` 回填与唯一索引重建） | 迁移后行为不变的库 | 3 |
| P2 | `access.py`：会话、角色、可见域、`can_read/can_write/can_manage`、设备/图纸解析器 | 权限唯一入口 | 2 |
| P3 | `/api/auth/*` + 登录页 + 强制改密 + 本地模式 | 能登录 | 3 |
| P4 | 管理后台：团队 CRUD、全量账号 CRUD、角色调整 | 账号可分配 | 3 |
| P5 | 项目级共享：`project_members` + 共享接口 + 共享弹窗 + 归属分配 | 队友可被拉进单个项目 | 3 |
| P6 | leader 团队管理：本团队建号/停用/重置密码（含提权防护） | leader 可自管团队 | 2 |
| P7 | 65 个既有 API + 9 条页面规则 + 19 个新接口收口（含 views/AI/tasks/devices/templates 双检、模板团队隔离） | 越权全部拦截 | 9.5 |
| P8 | 前端权限感知、403/401 处理、用户菜单、共享/团队/管理页、设备与模板权限 UI（含 admin 团队列/筛选） | 体验闭环 | 3.5 |
| P9 | 测试：172 个旧用例改造 + 约 80 个新用例 | 全绿 | 5.5 |
| P10 | 上线演练：迁移真实数据、双人验收、备份恢复、SSE/CSV 冒烟 | 上线 | 2 |
| | **合计** | | **约 38–41 人日** |

参考排期（单人）：约 7–8 周兼职 / 约 5 周全职；两人并行（一人 P3–P6 账号与共享，一人 P7 收口）可压到约 3 周。

风险缓冲建议 +10–15%，主要用于 P7 遗漏点、设备权限边界与 172 个旧用例改造的返工。

---

## 12. 风险登记册

| # | 风险 | 可能性 | 影响 | 应对 |
|---|---|---|---|---|
| R1 | 漏改某处跨项目查询导致越权读 | 中 | 高 | 集中式 `visible_project_sql()`；`test_tenant_isolation.py` 对**每个**聚合接口做双人对比；上线前用两个测试账号人工巡检 |
| R2 | 页面直接渲染他人数据 | 中 | 高 | 页面路由统一 `require_project` / `require_diagram`；TC-02 覆盖 |
| R3 | AI 工具越权枚举项目名 | 中 | 中高 | `_resolve_project` 解析后校验；工具调用全部走可见域；提示词中性措辞 |
| R4 | 迁移破坏存量数据 | 低 | 极高 | 迁移前 `backup()`；迁移后 `foreign_key_check` + 数量比对（含设备表）；先在备份库演练 |
| R5 | SQLite 写锁导致 500 | 低（低并发） | 中 | WAL + `busy_timeout`；2 worker；错误页可重试 |
| R6 | 宝塔 `open_basedir`/权限配置导致 502/500 | 中 | 中 | 按 9.4 逐步验证；`/healthz` 作为探针 |
| R7 | 公网暴露被撞库 | 中 | 高 | 登录限流 + 强密码 + 禁用弱口令 + 面板两步验证 |
| R8 | 备份文件本身泄露 | 低 | 高 | 备份目录不在站点根；权限 750；定期异机副本 |
| R9 | 管理员误操作（提升 leader、移动项目） | 中 | 中 | 高危操作二次确认；写入 `activity_log` |
| R10 | 成员离职后数据归属悬空 | 中 | 中 | 禁用而非删除；由 leader/admin 改 owner |
| R11 | 共享被当作后门：被共享 `edit` 的人删项目或改共享 | 中 | 高 | 三层权限拆分 + TC-16 强制覆盖 |
| R12 | leader 越权：自我提权、操作其他团队 | 中 | 高 | 服务端硬校验 + TC-19 |
| R13 | 共享记录残留：用户换团队后仍能访问旧项目 | 中 | 高 | 换团队事务内清除 `project_members`（INV-8）+ TC-21 扩展 |
| R14 | 设备/模板接口漏鉴权 | 中 | 高 | `require_device`/`require_diagram`/`require_template_read`/`require_template_write` 统一入口 + `test_devices_access.py`、`test_device_templates_scope.py` |
| R15 | 设备 CSV 含报价，被无权限用户导出 | 低 | 高 | 导出按项目读权限；TC-25 覆盖 |
| R16 | 本地免登录模式误开到公网 | 低 | 极高 | 本地模式只在启动器设置；`TOPOTASH_DEPLOY=production` 互斥校验；部署清单检查 |
| R17 | AI 流式接口被 Nginx 缓冲/超时 | 中 | 中 | `proxy_buffering off` + 300s 超时 + 冒烟测试 |
| R18 | 172 个旧用例改认证后“假绿” | 中 | 中 | 测试基座自动登录管理员，同时保留未登录 client 的 401 用例 |
| R19 | 迁移把 v5 误判为 v4 导致设备表回退 | 低 | 极高 | 版本守卫 `version >= 6`；迁移后校验 `schema_version` 与设备表数量 |
| R20 | 模板团队隔离漏改：跨团队可读/可写，或唯一索引仍为全局 | 中 | 高 | `visible_template_sql()` + `require_template_write()` 统一入口；唯一索引改为 `(team_id, name, brand, model)`；TC-24/28/29/30 覆盖 |
| R21 | 存量模板迁移后 `team_id` 为空，导致成员看不到或越权 | 低 | 高 | 迁移时全部回填默认团队；迁移后校验 `team_id IS NOT NULL`；INV-12 |

---

## 13. 待确认问题（Open Questions）

| # | 问题 | 结论 / 建议默认 |
|---|---|---|
| Q1 | 负责人是否需要「本团队只读」的观察员角色？ | 暂不需要；如需，`can_write` 加一个条件即可 |
| Q2 | 负责人能否管理本团队成员？ | **已定：能**。仅 member，不能创建 leader/admin、不能跨团队 |
| Q3 | 成员之间是否允许「显式共享单个项目」？ | **已定：需要**。`project_members`，同团队、项目级、view/edit 两档 |
| Q4 | 一个用户是否会属于多个团队？ | 暂一人一团队；升级路径见附录 C |
| Q5 | 是否需要「操作审计」页面？ | 暂不需要，仅落库 `activity_log`（含 actor） |
| Q6 | 域名是否需要备案？ | **已定：已有备案域名**，按 9.9 部署 |
| Q7 | 是否保留 `首次启动.bat`？ | **已定：保留**，本地免登录；线上用 Linux 部署流程 |
| Q8 | 共享是否要通知被共享人？ | 暂不做站内信；共享后对方列表与看板直接出现 |
| Q9 | 设备模板是否需要团队隔离？ | **已定：需要**。模板按 `team_id` 团队共享；本团队所有成员/负责人可编辑；其他团队不可见；管理员全局只读并可查看归属团队（D8） |
| Q10 | 设备 CSV 导出是否对所有可读用户开放？ | **已定：是**。与项目读权限一致；如报价敏感，可后续加「仅 owner/leader/admin 可导出」开关 |
| Q11 | 本地模式是否也要显示团队/管理入口？ | **已定：不显示**。本地模式只保留业务功能 |
| Q12 | 是否保留旧版 `static/apps/tasks/`？ | 保留，仅用于历史数据回看；不新增入口 |
| Q13 | 管理员是否需要编辑设备模板？ | **已定：不需要**。管理员只读查看全局模板与归属团队；如后续需要代管，放开 `require_template_write` 的 admin 分支即可 |
| Q14 | 人员换团队后，其创建的历史模板是否随人迁移？ | **已定：不迁移**。模板归属团队而非个人，换团队后只能编辑新团队模板；如需搬迁由运维在数据库层面处理，产品界面不提供跨团队搬迁 |

---

## 14. 实现后可达成的能力

### 14.1 部署形态

| 能力 | 说明 |
|---|---|
| 公网多人使用 | 一个 HTTPS 域名（已备案）+ 宝塔托管，团队通过浏览器访问 |
| 数据集中 | 项目/任务/图纸/设备存在服务器 SQLite，每日自动备份 |
| 离线版不受影响 | Windows 双击启动的本地模式继续可用，免登录 |
| 升级不丢数据 | `git pull` + 手工迁移，数据目录与代码分离 |

### 14.2 账号与登录

| 能力 | 说明 |
|---|---|
| 管理员建号 | 管理后台创建任意角色账号（含 leader） |
| leader 自助建号 | 团队 leader 可为本团队加普通成员 |
| 强制改密 | 新号/重置密码后首次登录必须改密 |
| 一键下线 | 停用、重置密码、改密都会立即让该用户所有会话失效 |
| 登录防护 | 连续失败锁定 15 分钟，密码 scrypt 哈希，Cookie 不可被 JS 读取 |
| 本地免登录 | 双击启动器直接进入，适合个人离线使用 |

### 14.3 团队与权限

| 能力 | 说明 |
|---|---|
| 默认隔离 | 成员只看到自己的项目；同事的项目在列表、看板、搜索、AI 里都不出现 |
| leader 全局视角 | leader 看到本团队全部项目，可直接编辑、删除、改归属 |
| 跨团队隔离 | leader 看不到其他团队；只有管理员能跨团队移动项目 |
| 归属分配 | leader 可把项目改派给本团队任一成员 |
| 三档权限 | 看：自己的 + 被共享的；改：owner/leader/admin 或 edit 共享；管：删项目/换 owner/管共享 |

### 14.4 项目级共享

| 能力 | 说明 |
|---|---|
| 按需拉人 | 项目所有者点「共享」，从同团队选人，选「可查看」或「可编辑」 |
| 只读协作 | 被共享为「查看」的同事能看项目全部内容，但改不了 |
| 协同编辑 | 被共享为「编辑」的同事能改任务、画布与设备 |
| 不可夺权 | 被共享的人不能删项目、不能改共享名单、不能换 owner |
| 随时收回 | 撤销共享后对方立即 404，列表与搜索同步消失 |
| 跨团队禁止 | 只能共享给同团队成员 |

### 14.5 日常业务功能（保持现状并加权限）

| 能力 | 说明 |
|---|---|
| 项目/阶段/看板 | 项目总览、四阶段看板、项目工作台，数量与统计按可见域计算 |
| 任务管理 | 任务列表、子任务、标签、优先级、到期、阶段看板 |
| 拓扑图 | 拓扑图库、类型缩略图、画布编辑、导入/导出、复制、绑定项目、删除 |
| 节点跟进 | 画布节点标记待跟进、与任务双向关联、节点状态回写 |
| **设备清单** | 方案级 BOM、类别/状态/数量/价格、CSV 导出、设备↔节点关联 |
| **设备模板库** | 团队共享预设；本团队所有成员/负责人可维护与 CSV 导入；其他团队不可见；管理员可查看全局模板与归属团队（只读） |
| 全局搜索 | 结果只落在可见域内 |
| AI 助手 | 管理员配 Key 后全员可用；会话按人隔离；草稿确认时再次校验权限 |

### 14.6 运维与安全

| 能力 | 说明 |
|---|---|
| 备份恢复 | 每日 03:00 自动备份、保留 14 天、可演练恢复 |
| 安全基线 | HTTPS + HSTS、CSRF、登录限流、`/data` 与 `.git` 不可访问 |
| 健康检查 | `/healthz` 供监控探针，生产不返回路径 |
| 运维可见性 | `activity_log` 记录操作者；宝塔可看访问/错误日志 |
| 备案合规 | 页脚展示备案号并链接工信部 |

### 14.7 明确仍然做不到的事

1. 成员不能自己注册、不能自己找回密码；
2. 共享只到「项目」这一层；
3. 不能临时授权（如「给他看 3 天」），撤销靠手工；
4. 不能跨团队协作；
5. 没有移动端 App；
6. 多人同时编辑同一张画布仍可能互相覆盖（`version` 冲突检测只提示，不强制锁）；
7. 设备模板只在本团队内共享，不能跨团队复制或共享；管理员对模板只读，不能代管；

---

## 附录 A：v6 DDL（新增与变更部分）

> v5 已有的 `projects` / `tasks` / `diagrams` / `devices` / `device_node_links` / `device_templates` 等表不重复列出；本附录只列 v6 新增表、`ALTER` 与索引变更。新库的 `schema.sql` 应直接把 `team_id` 写进 `device_templates` 的建表语句，并删除旧的全局唯一索引。

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin','leader','member')),
    team_id TEXT REFERENCES teams(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
    must_change_password INTEGER NOT NULL DEFAULT 1 CHECK (must_change_password IN (0,1)),
    session_epoch INTEGER NOT NULL DEFAULT 0,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (role = 'admin' OR team_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_users_team ON users(team_id, status);

CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access     TEXT NOT NULL DEFAULT 'view' CHECK (access IN ('view','edit')),
    granted_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_pm_user ON project_members(user_id, project_id);

CREATE TABLE IF NOT EXISTS login_throttle (
    key TEXT PRIMARY KEY,
    failures INTEGER NOT NULL DEFAULT 0,
    first_failure_at TEXT,
    locked_until TEXT,
    updated_at TEXT NOT NULL
);

ALTER TABLE projects         ADD COLUMN team_id       TEXT REFERENCES teams(id);
ALTER TABLE projects         ADD COLUMN owner_user_id TEXT REFERENCES users(id);
ALTER TABLE diagrams         ADD COLUMN owner_user_id TEXT REFERENCES users(id);
ALTER TABLE ai_conversations ADD COLUMN user_id       TEXT REFERENCES users(id);
ALTER TABLE activity_log     ADD COLUMN actor_user_id TEXT REFERENCES users(id);
ALTER TABLE device_templates ADD COLUMN team_id       TEXT REFERENCES teams(id);

CREATE INDEX IF NOT EXISTS idx_projects_team  ON projects(team_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_diagrams_owner ON diagrams(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_ai_conv_user   ON ai_conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_templates_team ON device_templates(team_id, category, name);

DROP INDEX IF EXISTS idx_device_templates_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_templates_team_key
    ON device_templates(team_id, name, brand, model);

INSERT OR REPLACE INTO app_meta(key, value) VALUES ('schema_version', '6');
```

`device_templates` 在 v6 的目标结构（供新库 `schema.sql` 使用）：

```sql
CREATE TABLE IF NOT EXISTS device_templates (
    id          TEXT PRIMARY KEY,
    team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,  -- 归属团队
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_templates_team_key
    ON device_templates(team_id, name, brand, model);
CREATE INDEX IF NOT EXISTS idx_device_templates_team
    ON device_templates(team_id, category, name);
```

> 旧库升级时不能直接加 `NOT NULL`，所以迁移函数先 `ADD COLUMN team_id TEXT`，回填默认团队后再由应用层保证非空；新库则直接按上面的 `NOT NULL` 建表。

## 附录 B：`access.py` 参考骨架（实现指南，非最终代码）

```python
"""统一认证与权限判定。所有蓝图与页面都从这里取用户、判定可见性。"""
from __future__ import annotations

from functools import wraps

from flask import g, request, session

from db import ApiError, get_db

PUBLIC_PATHS = {"/login", "/api/auth/login", "/healthz"}


def current_user() -> dict | None:
    if "user" in g:
        return g.user
    uid = session.get("uid")
    if not uid:
        g.user = None
        return None
    row = get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    user = dict(row) if row else None
    if user and (user["status"] != "active" or session.get("epoch") != user["session_epoch"]):
        user = None
    g.user = user
    return user


def _password_change_allowed() -> bool:
    return request.path.startswith("/api/auth/") or request.path.startswith("/static/")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            raise ApiError("请先登录", 401, "not_authenticated")
        if user["must_change_password"] and not _password_change_allowed():
            raise ApiError("请先修改初始密码", 403, "password_change_required")
        return view(*args, **kwargs)
    return wrapper


def _share_access(project_id: str, user_id: str) -> str | None:
    row = get_db().execute(
        "SELECT access FROM project_members WHERE project_id=? AND user_id=?",
        (project_id, user_id),
    ).fetchone()
    return row["access"] if row else None


def can_read(user, project) -> bool:
    if user["role"] == "admin":
        return True
    if user["role"] == "leader":
        return project["team_id"] == user["team_id"]
    if project["owner_user_id"] == user["id"]:
        return True
    return _share_access(project["id"], user["id"]) is not None


def can_write(user, project) -> bool:
    if user["role"] in ("admin", "leader"):
        return can_read(user, project)
    if project["owner_user_id"] == user["id"]:
        return True
    return _share_access(project["id"], user["id"]) == "edit"


def can_manage(user, project) -> bool:
    if user["role"] in ("admin", "leader"):
        return can_read(user, project)
    return project["owner_user_id"] == user["id"]


def visible_project_sql(user, alias="p"):
    if user["role"] == "admin":
        return "1=1", []
    if user["role"] == "leader":
        return f"{alias}.team_id = ?", [user["team_id"]]
    return (
        f"({alias}.owner_user_id = ? OR EXISTS (SELECT 1 FROM project_members pm"
        f" WHERE pm.project_id = {alias}.id AND pm.user_id = ?))",
        [user["id"], user["id"]],
    )


_NEED_FN = {"read": can_read, "write": can_write, "manage": can_manage}


def require_project(project_id: str, need: str = "read") -> dict:
    row = get_db().execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise ApiError(f"项目不存在：{project_id}", 404, "project_not_found")
    project = dict(row)
    if not _NEED_FN[need](current_user(), project):
        raise ApiError(f"项目不存在：{project_id}", 404, "project_not_found")
    return project


def require_device(device_id: str, need: str = "read") -> dict:
    row = get_db().execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        raise ApiError("设备不存在", 404, "device_not_found")
    device = dict(row)
    require_project(device["project_id"], need)
    return device


def require_diagram(diagram_id: str, need: str = "read") -> dict:
    row = get_db().execute("SELECT * FROM diagrams WHERE id=?", (diagram_id,)).fetchone()
    if not row:
        raise ApiError("图纸不存在", 404, "diagram_not_found")
    diagram = dict(row)
    if diagram["project_id"]:
        require_project(diagram["project_id"], need)
    else:
        user = current_user()
        is_owner = diagram.get("owner_user_id") == user["id"]
        is_leader = user["role"] == "leader" and _diagram_owner_team(diagram) == user["team_id"]
        if not (user["role"] == "admin" or is_leader or (is_owner and need != "manage")):
            raise ApiError("图纸不存在", 404, "diagram_not_found")
    return diagram


def require_admin() -> dict:
    user = current_user()
    if not user:
        raise ApiError("请先登录", 401, "not_authenticated")
    if user["role"] != "admin":
        raise ApiError("需要管理员权限", 403, "forbidden")
    return user


def visible_template_sql(user, alias="dt"):
    if user["role"] == "admin":
        return "1=1", []
    return f"{alias}.team_id = ?", [user["team_id"]]


def require_template_read(template_id: str) -> dict:
    row = get_db().execute(
        "SELECT * FROM device_templates WHERE id=?", (template_id,)
    ).fetchone()
    if not row:
        raise ApiError("模板不存在", 404, "template_not_found")
    user = current_user()
    if user["role"] != "admin" and row["team_id"] != user["team_id"]:
        raise ApiError("模板不存在", 404, "template_not_found")
    return dict(row)


def require_template_write(template_id: str | None = None) -> dict:
    """模板写权限：本团队所有成员/负责人；管理员只读；跨团队按不存在处理。"""
    user = current_user()
    if not user:
        raise ApiError("请先登录", 401, "not_authenticated")
    if user["role"] == "admin":
        raise ApiError("管理员对设备模板只读", 403, "forbidden")
    if not user["team_id"]:
        raise ApiError("当前账号没有团队", 403, "forbidden")
    if template_id:
        row = get_db().execute(
            "SELECT * FROM device_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not row or row["team_id"] != user["team_id"]:
            raise ApiError("模板不存在", 404, "template_not_found")
        return dict(row)
    return user
```

## 附录 C：未来升级为「一人多团队」的路径

若 Q4 变成「必须支持多团队」：

1. 新增 `team_members(team_id, user_id, role, joined_at)`，把 `users.team_id`/`users.role` 迁移进去；
2. `visible_project_sql` 从「等于我的团队」改为「`team_id IN (我所属团队)`」；leader 判定按 `(team_id, user_id)` 查角色；
3. `users.role` 降为全局角色（`admin` / `user`）；
4. `project_members` 的约束从「同团队」放宽为「项目所属团队 ∈ 目标用户的团队集合」；
5. **设备模板**已是团队级（v6 已加 `team_id`）；多团队时把可见域从 `team_id = 我的团队` 改为 `team_id IN (我所属团队)`，编辑权限改为「模板团队 ∈ 我所属团队」；
6. 前端增加「切换当前团队」，共享弹窗与模板页按当前团队过滤；
7. 迁移脚本与权限用例同步更新。

预估额外工作量：**4–5 人日**（本设计的集中式权限层可避免全量返工）。
