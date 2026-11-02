# TopoTash 设计说明

本文说明 TopoTash 的数据模型、存储结构、API 与前端架构。

---

## 1. 产品定位与模块边界

TopoTash 是面向 IT 售前工程师的项目工作台，核心对象只有三个：

- **项目**：售前商机 / 客户项目，带售前阶段与负责人
- **任务**：项目下的待办、子任务、标签、截止时间与循环规则
- **拓扑图**：项目下的系统架构图、逻辑拓扑、POC 部署图

三个对象的关系：

```
项目 1 ── N 任务
项目 1 ── N 拓扑图
任务 M ── N 拓扑图        （任务级关联）
拓扑图节点 M ── N 任务     （节点级关联，节点可标记待跟进）
```

前端由三个层次组成：

| 层 | 职责 |
|---|---|
| Shell | 侧栏项目导航、项目总览、阶段看板、拓扑图库、项目工作台 |
| 内置任务台 | 列表 / 看板、优先级、子任务、标签、循环任务、搜索、AI 助手 |
| 内置拓扑编辑器 | SVG 画布、设备模具、连线、对齐、组合、导出、节点跟进 |

任务台和拓扑编辑器都是自包含的单文件前端模块，通过桥接脚本接入 TopoTash API；它们不依赖任何外部服务或构建工具。

### 1.1 任务台数据模型

任务台在浏览器内的完整状态：

```json
{
  "version": "2.0",
  "lastModified": "2026-06-10T02:40:26.762Z",
  "projects": [
    { "id": "c_work", "name": "工作项目", "color": "#f59e0b", "createdAt": "..." }
  ],
  "tags": ["设计", "开发", "会议"],
  "tasks": [
    {
      "id": "t_xxx",
      "title": "完成产品需求文档 v2.0",
      "description": "……",
      "priority": 0,
      "status": "todo",
      "stage": "proposal",
      "dueDate": "2026-06-09T08:01:18.366Z",
      "recur": "weekly",
      "recurDay": 5,
      "projectId": "c_work",
      "tags": ["文档", "设计"],
      "subtasks": [{ "id": "st_xxx", "title": "用户故事梳理", "completed": true }],
      "order": 0,
      "createdAt": "…",
      "updatedAt": "…"
    }
  ],
  "aiConfig": { "apiBase": "", "apiKey": "", "model": "", "temperature": 0.7, "systemPrompt": "" },
  "aiChatHistory": []
}
```

字段语义：

- `priority`：0=P0 紧急、1=P1 重要、2=P2 一般、3=P3 低
- `status`：`todo` / `doing` / `done`
- `stage`：`research` / `proposal` / `poc` / `bidding`
- `recur`：`daily` / `weekly` / `monthly` / `quarterly` / `yearly`，`recurDay` 为周几（0-6）或几号（1-31）
- `projectId`：任务台内部的「任务分类」，映射到 `task_categories.id`
- `subtasks`：内嵌数组，`completed` 布尔值
- `order`：列表 / 看板排序

### 1.2 拓扑图数据模型

画布 JSON：

```json
{
  "app": "topotash",
  "version": 2,
  "saved": "2026-08-08T09:35:35.001Z",
  "shapes": {
    "n1": {
      "id": "n1", "type": "shape", "kind": "server",
      "x": 80, "y": 160, "w": 120, "h": 120,
      "rot": 0, "flipH": false, "flipV": false,
      "fill": "#5b6cf0", "stroke": "none", "strokeWidth": 1.6,
      "dash": null, "opacity": 1, "fillOpacity": 1, "radius": 10,
      "text": "应用服务器", "textColor": "#1f2329", "fontSize": 12.5,
      "fontFamily": "Microsoft YaHei", "bold": true, "italic": false,
      "textAlign": "center", "textVAlign": "middle",
      "imgFit": "fill", "image": null, "origRatio": null, "lockRatio": true,
      "fields": [{ "k": "IP", "v": "10.0.0.8" }, { "k": "CPU", "v": "23%" }]
    },
    "n2": {
      "id": "n2", "type": "connector", "kind": "line",
      "start": { "shapeId": "n1", "port": "E" },
      "end": { "shapeId": "n3", "port": "W" },
      "custom": false, "points": [],
      "stroke": "#3a4657", "strokeWidth": 1.6, "dash": null,
      "arrowStart": false, "arrowEnd": false, "text": "10GbE", "flow": "off"
    }
  },
  "order": ["n1", "n2", "n3"],
  "groups": {},
  "imagePool": {}
}
```

字段要点：

- `type`：`shape`（节点 / 基础图形 / 图片）或 `connector`（连线）
- `kind`：13 类网络设备（`server/db/switch/router/firewall/cloud/pc/laptop/phone/printer/globe/storage/cluster`）+ 基础图形（`rect/ellipse/diamond/text/image`）
- `start` / `end`：连线端点，可挂 `shapeId + port`（8 向端口），也可为自由坐标
- `points`：自定义折点；`custom` 表示是否手动改过走线
- `groups`：组合关系；`imagePool`：图片池，画布内图片引用 `imageId`
- `fields`：自定义字段，演示模式详情卡的数据源

TopoTash 不把画布拆表存储：`diagrams.content_json` 保存完整 JSON，另外把节点解析到 `diagram_nodes` 作为「可检索索引」，用于跨图查询与任务关联。

### 1.3 模块通信

| 场景 | 方式 |
|---|---|
| 任务台读取 / 保存项目状态 | 同源 `fetch` 调 `/api/projects/<id>/todo-state` |
| 拓扑编辑器读取 / 保存画布 | 同源 `fetch` 调 `/api/diagrams/<id>/content` |
| 拓扑编辑器打开任务 | `postMessage({type:'topotash:open-task', taskId})` 给父页面 |
| 保存状态、错误提示 | `postMessage({type:'topotash:visio-saved' / 'visio-error'})` |
| 项目数据变更 | `postMessage({type:'topotash:project-changed'})`，父页面刷新统计 |

---

## 2. 领域模型

```
projects 1 ─── N task_categories
    │ 1                 │ 1
    │ N                 │ N
  tasks 1 ─── N subtasks
    │ M
    │        task_tags  M ─── N tags
    │
    │ N                    N
    └──── task_diagrams ────┘
    │
    │ 1
    │ N
  diagrams 1 ─── N diagram_nodes 1 ─── N node_task_links N ─── 1 tasks
```

- **项目**是唯一入口：任务、拓扑图都必须属于一个项目。
- **任务分类**是项目内部的工作流分组，不是顶层项目。
- **节点-任务关联**是多对多：一个节点可以挂多个任务，`is_primary` 指定主任务；主任务状态驱动节点角标。
- **任务-拓扑图关联**是任务级弱关联（“确认 POC 环境” ↔ “POC 部署图”），与节点级关联互补。

---

## 3. SQLite Schema

完整建表语句见 [`schema.sql`](../schema.sql)。所有表启用外键级联；时间统一存 ISO-8601 UTC 字符串。

### 3.1 projects

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID（`p_` + 12 hex） |
| `name` | TEXT NOT NULL | 项目名 |
| `code` | TEXT | 商机 / 项目编号 |
| `customer` | TEXT | 客户 |
| `industry` | TEXT | 行业 |
| `owner` | TEXT | 售前负责人 |
| `stage` | TEXT CHECK | `research/proposal/poc/bidding` |
| `status` | TEXT CHECK | `active/won/lost/paused` |
| `description` | TEXT | 背景、目标、竞争态势 |
| `color` | TEXT | 卡片主题色 |
| `start_date` / `end_date` | TEXT | `YYYY-MM-DD` |
| `todo_config` | TEXT(JSON) | 任务台的 `aiConfig` / `aiChatHistory` |
| `metadata` | TEXT(JSON) | 预留扩展 |
| `created_at` / `updated_at` | TEXT | 时间戳 |

索引：`stage`、`status`、`updated_at`。

### 3.2 task_categories

`id`、`project_id`（FK CASCADE）、`name`、`color`、`sort_order`、`created_at`。

任务台的「项目」下拉直接读这张表；删除分类时任务 `category_id` 置 NULL（`ON DELETE SET NULL`）。

### 3.3 tasks

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | 兼容任务台的 12 位 id，也接受 UUID |
| `project_id` | TEXT FK | 所属项目，CASCADE |
| `category_id` | TEXT FK | 任务分类，SET NULL |
| `title` / `description` | TEXT | 标题 / 详情 |
| `priority` | INTEGER 0-3 | P0-P3 |
| `status` | TEXT | `todo/doing/done` |
| `stage` | TEXT | 任务所属售前阶段，可与项目阶段不同 |
| `due_date` | TEXT | ISO 时间 |
| `recur` / `recur_day` | TEXT / INT | 循环规则 |
| `sort_order` | REAL | 列表 / 看板排序 |
| `source` | TEXT | `manual/ai/diagram/import` |
| `completed_at` | TEXT | 完成时间 |
| `created_at` / `updated_at` | TEXT | 时间戳 |

索引：`(project_id, status)`、`stage`、`due_date`、`category_id`。

### 3.4 subtasks

`id`、`task_id`（CASCADE）、`title`、`completed`(0/1)、`sort_order`、`created_at`、`updated_at`。

### 3.5 tags / task_tags

- `tags(id INTEGER PK, project_id FK, name, color, created_at, UNIQUE(project_id,name))`
- `task_tags(task_id, tag_id, PRIMARY KEY(task_id, tag_id))`

标签是项目内共享池，避免不同项目的同名标签互相污染。

### 3.6 diagrams

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | UUID |
| `project_id` | TEXT FK | 所属项目，CASCADE |
| `name` / `description` | TEXT | 图纸名称 / 说明 |
| `kind` | TEXT | `topology/architecture/deployment/other` |
| `content_json` | TEXT | 完整画布 JSON（shapes/order/groups/imagePool） |
| `version` | INTEGER | 每次保存 +1 |
| `node_count` | INTEGER | 节点数（不含连线） |
| `created_at` / `updated_at` | TEXT | 时间戳 |

### 3.7 diagram_nodes

从 `content_json` 解析出的「节点索引」，保存画布时增量 upsert：

`id INTEGER PK`、`diagram_id` FK、`node_key`（画布 shape id）、`label`、`kind`、`x/y/w/h`、`followup_status`（`none/todo/doing/done`）、`note`、`synced_at`、`UNIQUE(diagram_id,node_key)`。

删除节点时同步删除 `node_task_links`，避免悬空关联。

### 3.8 node_task_links

| 字段 | 说明 |
|---|---|
| `diagram_id` + `node_key` | 定位节点 |
| `task_id` | FK tasks，CASCADE |
| `relation` | `followup/reference/blocker` |
| `is_primary` | 主任务标记（一个节点最多一个主任务） |
| `note` | 关联备注 |
| `created_at` | 时间戳 |

唯一约束 `(diagram_id,node_key,task_id)`；节点删除、任务删除、图纸删除都会级联清理。

### 3.9 task_diagrams

任务级关联：`task_id`、`diagram_id`、`relation`、`note`、`created_at`，唯一约束 `(task_id,diagram_id)`。

### 3.10 activity_log / app_meta

- `activity_log`：项目动态（create/update/delete/link），供项目概览展示。
- `app_meta`：`schema_version`，为后续 schema 迁移预留。

---

## 4. API 设计

完整请求 / 响应见 [`docs/API.md`](API.md)。这里说明两个重点关联接口。

### 4.1 任务关联拓扑图（任务级）

```
POST /api/tasks/<task_id>/diagrams
{ "diagram_id": "d_xxx", "relation": "related", "note": "POC 环境" }
→ 201 { "task_id": "...", "diagram_id": "...", "diagram_name": "..." }

DELETE /api/tasks/<task_id>/diagrams/<diagram_id>
→ 200 { "deleted": true }
```

约束：

- 图纸必须与任务同属一个项目（服务端校验，防止跨项目串数据）。
- 重复关联走 `ON CONFLICT ... DO UPDATE`，幂等。
- 任务台详情面板通过桥接脚本调用；成功后本地缓存即时更新。

### 4.2 拓扑图节点关联任务（节点级）

```
POST /api/diagrams/<did>/nodes/<node_key>/followup
{ "status": "todo" }                       // 只改节点角标
{ "task_id": "t_xxx" }                     // 关联已有任务，角标跟随任务状态
{ "create_task": { "title": "...", "priority": 1, "stage": "poc" } }
                                            // 创建任务并自动关联为主任务
→ 200 { "node": {...}, "task": {...} }
```

服务端行为：

1. 校验节点存在（必须先保存过画布）；
2. `create_task` 时以 `source=diagram` 创建任务，标题默认「跟进：<节点名>」，描述记录来源图纸与节点；
3. 关联任务时把该节点其它 link 的 `is_primary` 清零，再 upsert 当前任务为 primary；
4. 节点 `followup_status` 取任务状态（todo/doing/done）；
5. 返回完整节点（含 `linked_tasks`），前端直接替换内存里的 `shape.tt` 并重绘角标。

任务状态变化时，`services.sync_node_status_for_task()` 会把所有以该任务为 primary 的节点角标同步成新状态。

---

## 5. 前端架构

### 5.1 页面结构

```
┌──────────────────────────────────────────────────────────────┐
│ Sidebar 248px │ Topbar: 面包屑 / 全局搜索 / 新建项目          │
│  Logo         ├──────────────────────────────────────────────┤
│  项目总览      │ 页面内容（Jinja 骨架 + JS 渲染）              │
│  阶段看板      │                                              │
│  拓扑图库      │ 项目工作台：概览 / 任务 / 拓扑图 / 关联视图     │
│  项目列表      │   └─ 任务标签页 = iframe(任务台)              │
└──────────────────────────────────────────────────────────────┘
```

拓扑编辑器是独立路由（不套 Shell），顶部一条 50px 的 TopoTash 返回条 + 全屏 iframe，保证画布空间。

### 5.2 任务台桥接

桥接脚本（`topotash-todo-bridge.js`）：

- 读取 URL 的 `project_id`，首次 `GET /todo-state`，赋给任务台的 `store`，调用原 `renderAll()`；
- 覆盖 `saveStore()`：原逻辑 + 650ms 防抖 `PUT /todo-state`；
- 包装 `renderDetailPanel()`：在详情面板追加「关联拓扑图」区块（chips + 下拉）；
- 包装 `renderStatusbar()`：追加「已同步 / 同步中 / 同步失败」状态；
- 监听 `postMessage({type:'topotash:focus-task'})`，从其他页面跳转时自动选中任务；
- 删除任务时通过 `deleted_task_ids` 显式告知服务端，避免用「全量差集」误删其他入口刚创建的任务。

### 5.3 拓扑编辑器桥接

桥接脚本（`topotash-visio-bridge.js`）：

- 读取 `project_id/diagram_id`，`GET /content` 后替换画布 `model`，重置 id 计数器、历史栈；
- 覆盖 `commit()`：原提交逻辑 + 900ms 防抖 `PUT /content`；
- 覆盖 `saveDoc()`：不再下载文件，改为立即保存到服务端；
- 包装 `render()`：给带 `tt.status` 的节点加 SVG 角标；
- 包装 `syncProps()`：在属性面板顶部插入「TopoTash 跟进」区块；
- 角标点击：有主任务 → `postMessage` 给父页面跳转任务台；无任务 → 选中节点，显示创建/关联控件；
- 禁用本地草稿自动保存，避免不同图纸互相覆盖。

### 5.4 关键时序

**任务 → 拓扑图关联**

```
任务台详情面板
  └─ 选择拓扑图
       └─ POST /api/tasks/<id>/diagrams
            └─ 服务端校验同项目 → upsert task_diagrams
                 └─ 返回成功 → 桥接更新缓存 → 重新渲染 chips
```

**节点 → 任务**

```
拓扑编辑器选中节点
  └─ 属性面板「TopoTash 跟进」
       ├─ 标记状态 → POST /nodes/<key>/followup {status}
       ├─ 关联已有 → POST /nodes/<key>/followup {task_id}
       └─ 创建任务 → POST /nodes/<key>/followup {create_task}
            └─ 服务端创建 tasks(source=diagram) + node_task_links(primary)
                 └─ 返回 node+task → 替换 shape.tt → 重绘角标
                      └─ postMessage(project-changed) → 父页面刷新统计
```

---

## 6. 项目结构

见 [README 的目录结构](../README.md#目录结构)。关键文件：

| 文件 | 作用 |
|---|---|
| `app.py` | Flask 工厂、页面路由、CLI；`debug=True, port=5000` |
| `db.py` | `sqlite3` 连接（`foreign_keys=ON`、WAL）、事务、错误类型 |
| `schema.sql` | 单一 schema 来源，`init-db` 直接 `executescript` |
| `services.py` | 序列化 / 节点解析 / 任务同步 / 任务台状态 |
| `api/projects.py` | 项目 CRUD + 任务台全量状态双向同步 |
| `api/tasks.py` | 任务 / 子任务 / 标签 / 任务-图纸关联 |
| `api/diagrams.py` | 图纸 CRUD / 画布内容 / 节点索引 / 节点跟进 |
| `api/views.py` | 总览、阶段看板、关联视图、搜索等只读聚合 |
| `static/js/project.js` | 项目工作台四个标签页与 iframe 生命周期 |
| `static/js/editor.js` | 拓扑编辑器外壳与 postMessage 状态 |

---

## 7. 历史数据导入

脚本：`tools/migrate_json.py`。

### 7.1 任务 JSON 映射

| 任务 JSON | TopoTash | 说明 |
|---|---|---|
| `store.projects[]` | `task_categories` | 非拆分模式下保留为任务分类；`--split-projects` 时每个分类变成一个项目 |
| `store.tags[]` | `tags` | 项目内标签池 |
| `tasks[].id` | `tasks.id` | 保留原 id（冲突时重新生成） |
| `tasks[].projectId` | `tasks.category_id` | 通过映射表转换 |
| `tasks[].stage` | `tasks.stage` | 缺失时用 `--stage` |
| `tasks[].dueDate` | `tasks.due_date` | ISO 原样 |
| `tasks[].recur/recurDay` | `tasks.recur/recur_day` | 原样 |
| `tasks[].subtasks[]` | `subtasks` 表 | 保留 id / 完成状态 / 顺序 |
| `tasks[].tags[]` | `task_tags` | 自动补建标签 |
| `tasks[].createdAt/updatedAt` | 同名列 | 保留历史时间 |
| `aiConfig/aiChatHistory` | `projects.todo_config` | JSON 原样保存 |

### 7.2 画布 JSON 映射

| 画布 JSON | TopoTash |
|---|---|
| 整个 JSON | `diagrams.content_json` |
| `shapes[*].type == "shape"` | `diagram_nodes` 一行 |
| `shapes[*].text` 首行 | `diagram_nodes.label` |
| `shapes[*].kind` | `diagram_nodes.kind` |
| `shapes[*].x/y/w/h` | 同名列 |
| 文件名 | `diagrams.name`（去掉 `.vweb.json`） |

迁移后的节点默认 `followup_status='none'`，不会凭空生成任务关联。

### 7.3 执行示例

```bash
python tools/migrate_json.py --todo data/todos.json --project-name "历史任务迁移"
python tools/migrate_json.py --todo data/todos.json --visio data/diagrams --visio-project "历史任务迁移"
```

---

## 8. 取舍与后续

**为什么任务台用全量 PUT，而不是逐任务 PATCH？**

任务台的一次用户操作会同时改任务、子任务、标签、排序甚至循环日期，逐字段 diff 容易漏；项目级数据量小（几十到几百个任务），全量 upsert 在一个事务里更稳。服务端对 `deleted_task_ids` 做显式删除，避免并发入口误删。

**为什么节点索引单独建表，而不每次解析 JSON？**

项目总览、阶段看板、关联视图需要跨图纸查询「哪些节点待跟进」「某任务关联了哪些节点」。SQLite 查询 `diagram_nodes`/`node_task_links` 比在 Python 里解析几十张图的 JSON 更直接，也能用外键保证删除一致性。

**后续可做**：

1. 拓扑图真实缩略图（保存时前端导出 PNG，服务端存文件 / 缩略图字段）。
2. 冲突检测：`PUT content` 带上客户端 `version`，不匹配返回 409。
3. 任务拖拽到阶段看板列 → PATCH `stage`，实现看板双向操作。
4. 项目归档 / 模板 / 导入导出整包（项目 + 图 + 任务）。
5. 认证与多用户（当前明确是本地单用户工具）。
