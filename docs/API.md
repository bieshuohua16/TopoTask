# TopoTash REST API

Base URL：`http://127.0.0.1:5000/api`
Content-Type：`application/json; charset=utf-8`
时间：ISO-8601 UTC，例如 `2026-11-02T08:06:20Z`
ID：项目/任务/图纸为字符串（`p_` / `t_` / `d_` / `c_` 前缀），节点为画布内 `n1`、`n2`…

错误格式：

```json
{ "error": { "code": "task_not_found", "message": "任务不存在：t_xxx" } }
```

常见状态码：`200` 成功、`201` 创建、`400` 参数错误、`404` 资源不存在、`409`（预留）、`500` 服务端错误。

---

## 1. 项目 Projects

### `GET /api/projects`

查询参数：

| 参数 | 说明 |
|---|---|
| `stage` | `research/proposal/poc/bidding`，`all` 或不传为全部 |
| `status` | `active/won/lost/paused` |
| `q` | 名称 / 客户 / 编号 / 负责人模糊搜索 |

响应：

```json
{
  "items": [
    {
      "id": "p_f1cfaf273131",
      "name": "星海银行 私有云 POC",
      "customer": "星海银行",
      "owner": "张伟",
      "stage": "poc",
      "stage_label": "POC 验证",
      "status": "active",
      "status_label": "跟进中",
      "color": "#4f5bd5",
      "task_total": 9,
      "task_done": 2,
      "task_open": 7,
      "task_progress": 22,
      "diagram_count": 2,
      "followup_count": 4,
      "next_due": "2026-11-04T10:00:00Z",
      "updated_at": "2026-11-02T08:06:20Z"
    }
  ],
  "total": 4,
  "stages": [{ "key": "research", "label": "需求调研", "hint": "…" }],
  "statuses": [{ "key": "active", "label": "跟进中" }]
}
```

### `POST /api/projects`

```json
{
  "name": "XX 银行 私有云 POC",
  "customer": "XX 银行",
  "owner": "张伟",
  "stage": "poc",
  "status": "active",
  "description": "…",
  "color": "#4f5bd5",
  "start_date": "2026-11-01",
  "end_date": "2026-12-31",
  "code": "PS-2026-018",
  "industry": "金融"
}
```

`name` 必填。创建成功返回 `201` + 项目对象；同时自动创建一个「默认分类」。

### `GET /api/projects/<project_id>`

返回项目 + 统计 + `recent_tasks`（最多 8 个未完成）、`diagrams`、`followup_nodes`、`activity`。

### `PATCH /api/projects/<project_id>`

请求体为任意项目字段子集，例如 `{ "stage": "bidding" }`。返回更新后的项目对象。

### `DELETE /api/projects/<project_id>`

级联删除任务、分类、标签、图纸、节点、关联、动态。返回：

```json
{ "deleted": true, "id": "p_xxx", "name": "XX 银行" }
```

### `GET /api/projects/<project_id>/todo-state`

返回任务台可直接消费的完整状态：

```json
{
  "version": "2.0",
  "lastModified": "2026-11-02T08:06:20Z",
  "projects": [{ "id": "c_xxx", "name": "默认分类", "color": "#6366f1", "createdAt": "…" }],
  "tags": ["POC", "网络"],
  "tasks": [
    {
      "id": "t_xxx",
      "title": "确认 POC 环境与到货时间",
      "description": "…",
      "priority": 0,
      "status": "todo",
      "stage": "poc",
      "dueDate": "2026-11-04T18:00:00Z",
      "recur": null,
      "recurDay": null,
      "projectId": "c_xxx",
      "source": "manual",
      "tags": ["POC"],
      "subtasks": [{ "id": "st_xxx", "title": "确认机柜位置", "completed": true }],
      "order": 0,
      "createdAt": "…",
      "updatedAt": "…"
    }
  ],
  "aiConfig": {},
  "aiChatHistory": [],
  "topotash": {
    "projectId": "p_xxx",
    "projectName": "星海银行 私有云 POC",
    "stage": "poc",
    "stageLabel": "POC 验证"
  }
}
```

### `PUT /api/projects/<project_id>/todo-state`

任务台桥接脚本使用。请求体与 GET 相同，另外支持：

```json
{ "deleted_task_ids": ["t_old_1", "t_old_2"] }
```

行为：

1. upsert 分类，删除本次未出现的分类（任务 `category_id` 置 NULL）；
2. 逐任务 upsert（保留原有 `stage`，若携带则更新）；子任务按数组替换；
3. 显式删除 `deleted_task_ids`；
4. 同步标签池与任务标签；
5. 保存 `aiConfig/aiChatHistory` 到 `projects.todo_config`；
6. 返回最新 `todo-state`。

---

## 2. 任务 Tasks

### `GET /api/tasks`

查询参数：

| 参数 | 说明 |
|---|---|
| `project_id` | 项目过滤 |
| `stage` | 阶段过滤 |
| `status` | `todo/doing/done/all` |
| `priority` | 0-3 |
| `q` | 标题 / 描述搜索 |
| `tag` | 标签名 |
| `diagram_id` | 只返回关联该图纸的任务 |
| `due` | `today/week/overdue/none` |
| `limit` / `offset` | 分页，默认 200 / 0 |
| `order` | `updated` 按更新时间，否则按状态+优先级+截止 |

响应：

```json
{
  "items": [
    {
      "id": "t_xxx", "project_id": "p_xxx", "project_name": "…",
      "category_id": "c_xxx", "title": "…", "description": "…",
      "priority": 1, "priority_label": "P1 重要",
      "status": "doing", "status_label": "进行中",
      "stage": "poc", "stage_label": "POC 验证",
      "due_date": "…", "recur": null, "recur_day": null,
      "sort_order": 1, "source": "manual",
      "tags": ["POC"], "subtasks": [], "subtask_total": 0, "subtask_done": 0,
      "diagrams": [{ "id": "d_xxx", "name": "POC 部署图", "kind": "deployment", "relation": "related" }],
      "created_at": "…", "updated_at": "…"
    }
  ],
  "total": 20, "limit": 200, "offset": 0
}
```

### `POST /api/tasks`

```json
{
  "project_id": "p_xxx",
  "title": "确认 POC 环境",
  "description": "…",
  "priority": 1,
  "status": "todo",
  "stage": "poc",
  "category_id": "c_xxx",
  "due_date": "2026-11-10T10:00:00Z",
  "recur": null,
  "recur_day": null,
  "tags": ["POC"],
  "subtasks": [{ "title": "确认机柜", "completed": false }]
}
```

未传 `category_id` 时自动归入项目第一个分类；未传 `stage` 时继承项目阶段。返回 `201` + 任务详情。

### `GET /api/tasks/<task_id>`

返回任务详情，额外包含：

```json
{
  "node_links": [{ "diagram_id": "d_xxx", "node_key": "n4", "is_primary": 1, "diagram_name": "…", "node_label": "计算节点" }],
  "diagrams": [{ "id": "d_xxx", "name": "…", "kind": "…", "relation": "related" }]
}
```

### `PATCH /api/tasks/<task_id>`

任意字段子集：`title/description/priority/status/stage/category_id/due_date/recur/recur_day/sort_order/tags/subtasks`。

状态变为 `done` 时写 `completed_at`，并同步所有以该任务为主任务的节点角标。

### `DELETE /api/tasks/<task_id>`

删除任务并级联删除子任务、标签关联、任务-图纸关联、节点-任务关联；若节点没有其它关联任务，角标重置为 `none`。

### 子任务

```
POST   /api/tasks/<task_id>/subtasks
PATCH  /api/tasks/<task_id>/subtasks/<subtask_id>
DELETE /api/tasks/<task_id>/subtasks/<subtask_id>
```

`POST` body：`{ "title": "确认机柜", "completed": false }`。

### 标签

`PUT /api/tasks/<task_id>/tags`

```json
{ "tags": ["POC", "网络"] }
```

### 任务 ↔ 拓扑图

`POST /api/tasks/<task_id>/diagrams`

```json
{ "diagram_id": "d_xxx", "relation": "related", "note": "POC 环境" }
```

校验图纸与任务同项目；重复关联幂等。返回 `201`。

`DELETE /api/tasks/<task_id>/diagrams/<diagram_id>`

```json
{ "deleted": true, "task_id": "t_xxx", "diagram_id": "d_xxx" }
```

---

## 3. 拓扑图 Diagrams

### `GET /api/diagrams`

参数：`project_id`、`unbound=1`、`q`。`unbound=1` 只返回未绑定项目的图纸。响应：

```json
{
  "items": [
    {
      "id": "d_xxx", "project_id": "p_xxx", "project_name": "…",
      "name": "POC 环境部署图", "kind": "deployment", "description": "…",
      "version": 3, "node_count": 7,
      "followup_count": 3, "linked_task_count": 3, "task_link_count": 3,
      "created_at": "…", "updated_at": "…"
    }
  ],
  "total": 2
}
```

未绑定项目的图纸 `project_id` 为 `null`、`project_name` 为空字符串。

### `POST /api/diagrams`

```json
{ "project_id": "p_xxx", "name": "POC 部署图", "kind": "deployment", "description": "…" }
```

`project_id` 可省略或传 `null`，此时图纸只存在拓扑图库、不绑定项目。可选传 `content`（完整画布 JSON）；不传则创建空白画布。

### `POST /api/diagrams/import`

从画布 JSON（例如编辑器导出的 `.vweb.json`）导入一张拓扑图：

```json
{
  "project_id": "p_xxx",
  "source_name": "gpu_cluster_topology.vweb.json",
  "name": "GPU 集群拓扑（可省略，默认取文件名）",
  "kind": "topology",
  "description": "可省略，默认记录来源文件",
  "content": { "shapes": { "n1": {} }, "order": ["n1"], "groups": {}, "imagePool": {} }
}
```

`project_id` 可省略（导入到拓扑图库、不绑定项目）。`content` 必须含 `shapes` 对象，否则返回 `400 invalid_content`。服务端会去除运行时 `tt` 元数据、解析节点索引；同名图纸自动追加序号（`xxx (2)`）。成功返回 `201` 与图纸对象。

### `GET /api/diagrams/<diagram_id>`

返回图纸元信息、`nodes`（含 `linked_tasks`）、`task_links`。

### `PATCH /api/diagrams/<diagram_id>`

`name/kind/description/project_id` 任意子集。传 `project_id` 即把图纸绑定 / 移动到另一个项目；跨项目的节点任务关联与任务级图纸关联会自动解除，并在两个项目的动态中各记一条日志。响应额外包含 `project_name`。

### `POST /api/diagrams/<diagram_id>/duplicate`

复制一张拓扑图：

```json
{ "name": "POC 部署图 副本（可省略）", "project_id": "p_xxx（可省略，默认同项目；原图未绑定时仍不绑定）" }
```

复制画布与节点索引；不复制节点任务关联和任务级图纸关联。返回 `201` 与新图纸对象。

### `DELETE /api/diagrams/<diagram_id>`

级联删除节点与全部关联。

### `GET /api/diagrams/<diagram_id>/content`

返回完整画布 JSON，并为每个节点注入：

```json
"tt": {
  "status": "todo",
  "label": "计算节点 ×3",
  "nodeKey": "n4",
  "tasks": [{ "id": "t_xxx", "title": "…", "status": "todo", "primary": true }]
}
```

同时返回 `_topotash`：`diagramId/diagramName/projectId/projectName/stage/version/nodeCount`。

### `PUT /api/diagrams/<diagram_id>/content`

```json
{
  "content": {
    "app": "topotash",
    "version": 2,
    "shapes": { "n1": { "id": "n1", "type": "shape", "kind": "server", "x": 100, "y": 100, "w": 120, "h": 120, "text": "应用服务器" } },
    "order": ["n1"],
    "groups": {},
    "imagePool": {}
  }
}
```

服务端会：

- 校验 `shapes` 是对象；
- 移除运行时注入的 `tt` 与 `_topotash`；
- `version + 1`；
- 解析节点 upsert 到 `diagram_nodes`，删除已移除节点及其关联；
- 更新 `node_count/updated_at`。

响应：

```json
{ "saved": true, "diagram_id": "d_xxx", "version": 4, "node_count": 7, "updated_at": "…" }
```

### `GET /api/diagrams/<diagram_id>/nodes`

```json
{
  "items": [
    {
      "node_key": "n4", "label": "计算节点 ×3", "kind": "server",
      "x": 250, "y": 250, "w": 120, "h": 120,
      "followup_status": "todo", "note": "",
      "linked_tasks": [
        { "task_id": "t_xxx", "title": "…", "status": "todo", "is_primary": 1 }
      ],
      "primary_task": { "task_id": "t_xxx", "…": "…" }
    }
  ]
}
```

### `PATCH /api/diagrams/<diagram_id>/nodes/<node_key>`

```json
{ "followup_status": "doing", "note": "等待客户确认" }
```

### `POST /api/diagrams/<diagram_id>/nodes/<node_key>/followup`

三种用法：

**只改角标**

```json
{ "status": "doing" }
```

**关联已有任务（设为主任务）**

```json
{ "task_id": "t_xxx" }
```

**创建任务并关联**

```json
{
  "create_task": {
    "title": "跟进：核心交换机",
    "description": "…",
    "priority": 1,
    "stage": "poc",
    "due_date": null,
    "tags": ["拓扑跟进"]
  }
}
```

响应：

```json
{
  "node": { "node_key": "n2", "followup_status": "todo", "linked_tasks": ["…"] },
  "task": { "id": "t_xxx", "title": "跟进：核心交换机", "status": "todo", "stage": "poc" }
}
```

`create_task` 时任务 `source=diagram`，默认标题「跟进：<节点名>」，默认阶段继承项目阶段，未指定分类时归入项目默认分类。

### `POST /api/diagrams/<diagram_id>/nodes/<node_key>/links`

追加关联（不抢占主任务）：

```json
{ "task_id": "t_xxx", "relation": "reference", "is_primary": false, "note": "" }
```

### `DELETE /api/diagrams/<diagram_id>/nodes/<node_key>/links/<task_id>`

删除关联，返回节点最新状态；若还有其它关联，角标跟随剩余任务状态，否则重置为 `none`。

---

## 4. 聚合视图 Views

### `GET /api/views/overview`

```json
{
  "project_total": 4, "active_projects": 3, "won_projects": 0,
  "task_total": 20, "task_done": 2, "task_open": 18, "task_overdue": 0,
  "diagram_total": 4, "followup_total": 5,
  "stage_stats": [
    { "key": "research", "label": "需求调研", "hint": "…",
      "project_count": 1, "task_count": 4, "open_task_count": 4, "done_task_count": 0 }
  ],
  "projects": ["项目对象 + 统计"],
  "upcoming": ["任务对象"],
  "followups": ["节点 + 关联任务"],
  "stages": ["阶段字典"]
}
```

### `GET /api/views/stage-board`

参数：`project_id`、`include_done=1`。响应：

```json
{
  "stages": [
    {
      "key": "poc", "label": "POC 验证", "hint": "环境部署、测试验证、问题闭环",
      "task_count": 5, "project_count": 2,
      "tasks": ["任务对象（含 project_name/diagrams）"]
    }
  ],
  "projects": ["项目对象"],
  "include_done": false,
  "project_id": null
}
```

### `GET /api/views/links`

参数：`project_id`（可选）。

```json
{
  "diagrams": [
    { "id": "d_xxx", "name": "…", "nodes": ["含 linked_tasks 的节点"] }
  ],
  "task_links": [
    { "task_id": "t_xxx", "title": "…", "status": "doing",
      "diagram_id": "d_xxx", "diagram_name": "…", "project_name": "…" }
  ]
}
```

### `GET /api/views/search?q=`

```json
{
  "projects": ["项目对象"],
  "tasks": ["任务对象"],
  "diagrams": ["图纸对象"]
}
```

---

## 5. AI 助手

AI 使用全局配置（不按项目区分），模型请求由 Flask 代理发出，浏览器拿不到 API Key。所有写操作只生成草稿，确认后才写库。

### `GET /api/ai/config`

```json
{
  "api_base": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "temperature": 0.7,
  "system_prompt": "",
  "api_key_set": true,
  "api_key_hint": "••••1234",
  "configured": true,
  "presets": [{"key": "deepseek", "label": "DeepSeek", "api_base": "...", "model": "deepseek-chat"}]
}
```

`api_key` 永远不会返回；`configured` 为 `true` 时才能聊天。

### `PUT /api/ai/config`

```json
{
  "api_base": "https://api.deepseek.com/v1",
  "api_key": "sk-...",       // 留空 / 不传 = 保持原 Key；clear_key=true 清空
  "model": "deepseek-chat",
  "temperature": 0.7,
  "system_prompt": ""
}
```

返回同 `GET`。缺少 `api_base` / `model` 返回 400。

### `POST /api/ai/test`

```json
{ "api_base": "https://api.deepseek.com/v1", "api_key": "sk-...", "model": "deepseek-chat" }
→ { "ok": true, "model": "deepseek-chat", "reply": "OK" }
```

失败时返回 `{ "ok": false, "error": "..." }`（HTTP 200，便于设置弹窗内联展示）。

### `GET /api/ai/conversations`

```json
{ "items": [{ "id": "cv_xxx", "title": "新建一个 POC 项目", "project_id": "p_xxx",
              "project_name": "XX 银行", "message_count": 6,
              "created_at": "...", "updated_at": "..." }] }
```

`POST /api/ai/conversations` 可传 `{"project_id": "p_xxx"}`；`DELETE /api/ai/conversations/<id>` 删除会话及其消息、草稿。

### `GET /api/ai/conversations/<id>`

```json
{
  "conversation": { "id": "cv_xxx", "title": "..." },
  "messages": [
    { "id": 1, "role": "user", "content": "帮我建一个项目", "meta": {} },
    { "id": 2, "role": "assistant", "content": "", "tool_calls": [ ... ] },
    { "id": 3, "role": "tool", "name": "create_project", "content": "{...}" },
    { "id": 4, "role": "assistant", "content": "已生成草稿，请确认。" }
  ],
  "actions": [ { "id": "a_xxx", "kind": "create_project", "status": "pending",
                 "title": "新建项目「...」", "form": [ ... ], "values": { ... },
                 "summary": ["客户：..."], "warning": "" } ]
}
```

### `POST /api/ai/chat`

```json
{
  "conversation_id": "cv_xxx",              // 可空，空则新建
  "message": "帮我新建一个售前项目",
  "context": { "page": "project", "project_id": "p_xxx" }
}
```

返回本次新增的消息与草稿：

```json
{
  "ok": true,
  "conversation": { "id": "cv_xxx", "title": "..." },
  "messages": [ { "role": "user", "content": "..." }, { "role": "assistant", "content": "..." } ],
  "actions": [ { "id": "a_xxx", "kind": "create_project", "status": "pending" } ]
}
```

- `ok=false` 时带 `error`；未配置模型时 `need_config=true`。
- 服务端最多执行 6 轮工具调用。
- 读工具：`list_projects / get_project / portfolio_summary / list_tasks / get_task / search`。
- 写工具：`create_project / update_project / delete_project / create_task / update_task / delete_task`，只返回草稿，不写业务表。

### `POST /api/ai/actions/<id>/confirm`

```json
{ "values": { "name": "XX 银行 POC", "stage": "poc", "starter_tasks": "POC 验证 | 确认环境" } }
→ { "action": { "id": "a_xxx", "status": "applied", "result": { "project_id": "p_xxx", "task_count": 2 } } }
```

`values` 可覆盖草稿字段（用户在卡片里修改）。草稿只能应用一次；重复确认返回 409。`POST /api/ai/actions/<id>/cancel` 取消草稿。

---

## 6. 调用示例

```bash
# 新建项目
curl -X POST http://127.0.0.1:5000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"XX 银行 POC","customer":"XX 银行","stage":"poc"}'

# 新建任务
curl -X POST http://127.0.0.1:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"project_id":"p_xxx","title":"确认 POC 环境","stage":"poc","priority":1}'

# 任务关联拓扑图
curl -X POST http://127.0.0.1:5000/api/tasks/t_xxx/diagrams \
  -H "Content-Type: application/json" -d '{"diagram_id":"d_xxx"}'

# 节点标记待跟进并创建任务
curl -X POST http://127.0.0.1:5000/api/diagrams/d_xxx/nodes/n4/followup \
  -H "Content-Type: application/json" \
  -d '{"create_task":{"title":"确认计算节点到货","priority":1,"stage":"poc"}}'

# 阶段看板
curl "http://127.0.0.1:5000/api/views/stage-board?include_done=1"

# 配置 AI（一次即可，全局生效）
curl -X PUT http://127.0.0.1:5000/api/ai/config \
  -H "Content-Type: application/json" \
  -d '{"api_base":"https://api.deepseek.com/v1","api_key":"sk-...","model":"deepseek-chat"}'

# 发起对话（会返回草稿 action）
curl -X POST http://127.0.0.1:5000/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我新建一个 XX 银行 POC 项目","context":{"page":"dashboard"}}'

# 确认草稿
curl -X POST http://127.0.0.1:5000/api/ai/actions/a_xxx/confirm \
  -H "Content-Type: application/json" \
  -d '{"values":{"name":"XX 银行 POC","stage":"poc"}}'
```

PowerShell 里用 `Invoke-RestMethod` 时注意 UTF-8；建议用 `-ContentType 'application/json; charset=utf-8'` 并传 UTF-8 字节。
