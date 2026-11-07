# 设备清单与拓扑联动 · 原型与设计说明

> 状态：v1 设备清单已实现；v2 型号角标/模板库迭代见 [README-v2.md](README-v2.md)。本目录保留最初的静态原型和设计说明；实际界面见 [13-project-devices-v2.png](../../screenshots/13-project-devices-v2.png)、[15-topology-device-panel.png](../../screenshots/15-topology-device-panel.png)。
> 首版已确认：保留价格字段；类别为 服务器/存储/网络/安全/软件/其他；状态为 规划中/已选型/已报价/已下单/已到货；按原型做拓扑联动；包含清单、CSV 导出和拓扑节点关联。

## 1. 原型图

| 页面 | 图片 |
|---|---|
| 项目工作台 · 设备清单标签页 | [01-device-tab.png](01-device-tab.png) |
| 新增 / 编辑设备弹窗 | [02-device-modal.png](02-device-modal.png) |
| 拓扑图 · 节点设备联动 | [03-topology-device.png](03-topology-device.png) |

对应静态页面：

- [device-tab.html](device-tab.html)（`?modal=1` 显示编辑弹窗）
- [topology-device.html](topology-device.html)

## 2. 目标

在每个项目下维护一份**方案级设备清单（BOM）**，并让设备与拓扑图节点建立双向关联：

- 项目工作台新增第 5 个标签页「设备清单」，排在「关联视图」之后。
- 设备清单覆盖技术参数、数量、类别、状态，可选单价/小计，供方案与报价阶段使用。
- 拓扑节点可以关联一个或多个设备；节点上显示设备角标；点击角标选中节点并在属性面板查看/关联设备。
- 设备清单里的「关联拓扑」可以直接打开对应图纸并选中节点。
- 节点删除只解除关联，不删除设备；设备删除会级联清理关联。

## 3. 页面与交互

### 3.1 设备清单标签页

- 顶部 4 个摘要：设备种类、总数量、已关联拓扑（种类/节点）、预估金额。
- 工具栏：搜索、状态筛选、「仅看未关联拓扑」、导出 CSV、从拓扑生成（可选）、新增设备。
- 类别筛选：全部 / 网络设备 / 安全设备 / 服务器 / 存储 / 软件许可 / 其他。
- 表格列：设备（名称 + 品牌型号）、类别、关键参数、数量、状态、关联拓扑、小计、操作。
- 行点击或「⋯」打开编辑弹窗；关联拓扑列的节点 chip 点击跳转到拓扑图并选中该节点。
- 金额列可整体隐藏；单价为空时不参与合计。
- 空状态：还没有设备 → 「从拓扑图节点生成」或「手动新增」。

### 3.2 新增 / 编辑设备

字段分三组：

1. **基本信息**：设备名称、类别、品牌、型号、关键参数/配置。
2. **数量与商务**：数量、单位、状态、单价、供应商、负责人、备注。
3. **关联拓扑节点**：已关联节点 chip + 「+ 选择节点」；可关联多张图、多个节点，关联时可填本节点数量（默认等于设备数量）。

建议的类别与状态（已按最终确认实现）：

- 类别：`server` 服务器、`storage` 存储、`network` 网络、`security` 安全、`software` 软件、`other` 其他。
- 状态：`planned` 规划中、`selected` 已选型、`quoted` 已报价、`ordered` 已下单、`delivered` 已到货。
- 单位：台 / 套 / 节点 / 个 / 块，默认「台」。

### 3.3 拓扑图内的联动

右侧属性面板在现有「TopoTash 跟进」上方新增「TopoTash 设备」区块：

- 列出当前节点关联的设备（名称、品牌型号、本节点数量、设备状态）。
- 操作：打开设备（跳到设备清单并定位）、取消关联。
- 「关联已有设备…」下拉：只列出本项目、尚未关联到该节点的设备。
- 「+ 新建并关联设备」：弹出轻量表单（名称默认取节点文本、类别按节点 `kind` 推断、数量默认 1），保存后同时创建并关联。
- 节点左上角显示设备角标 `设备 ×N`（N = 该节点所有设备关联数量之和）；右上角继续保留原有跟进角标。
- 点击设备角标：选中节点，右侧滚动到设备区块；点击跟进角标仍按原逻辑打开任务。
- 设备清单的节点 chip → `/projects/<pid>/diagrams/<did>?node=<key>`，复用现有节点定位。
- 拓扑里的「打开设备」→ `/projects/<pid>?tab=devices&device=<id>`，设备清单定位并高亮该行（不自动打开编辑弹窗，避免误改）。

## 4. 数据模型（建议）

```sql
CREATE TABLE devices (
  id          TEXT PRIMARY KEY,              -- d_xxx
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL DEFAULT 'other', -- network/security/server/storage/software/other
  brand       TEXT NOT NULL DEFAULT '',
  model       TEXT NOT NULL DEFAULT '',
  spec        TEXT NOT NULL DEFAULT '',
  quantity    INTEGER NOT NULL DEFAULT 1,
  unit        TEXT NOT NULL DEFAULT '台',
  status      TEXT NOT NULL DEFAULT 'planned', -- planned/selected/quoted/ordered/delivered
  unit_price  REAL,                           -- 可空；空值不参与合计
  currency    TEXT NOT NULL DEFAULT 'CNY',
  vendor      TEXT NOT NULL DEFAULT '',
  owner       TEXT NOT NULL DEFAULT '',
  note        TEXT NOT NULL DEFAULT '',
  sort_order  REAL NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE device_node_links (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id  TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  diagram_id TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
  node_key   TEXT NOT NULL,
  quantity   INTEGER NOT NULL DEFAULT 1,      -- 本节点部署数量
  note       TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (device_id, diagram_id, node_key)
);
```

关键约束：

- 设备必须属于一个项目；拓扑图必须与设备同项目，服务端校验。
- 节点删除：`sync_diagram_nodes` 清理 `device_node_links` 中该 `diagram_id + node_key`。
- 图纸删除：级联清理设备关联，设备保留。
- 设备删除：级联清理关联。
- 图纸迁移到其他项目：先清空该图的设备关联（与现有任务关联迁移策略一致），避免跨项目串数据。
- 复制图纸：不复制设备关联（与任务关联一致）。
- 汇总：`total = quantity * COALESCE(unit_price, 0)`；金额只用于方案估算，不含折扣/税。

## 5. API 草案

```
GET    /api/devices?project_id=&category=&status=&q=&linked=
POST   /api/devices
PATCH  /api/devices/<device_id>
DELETE /api/devices/<device_id>
GET    /api/projects/<project_id>/devices/summary
GET    /api/projects/<project_id>/devices/export.csv

POST   /api/devices/<device_id>/nodes
DELETE /api/devices/<device_id>/nodes/<diagram_id>/<node_key>
POST   /api/diagrams/<diagram_id>/nodes/<node_key>/devices
DELETE /api/diagrams/<diagram_id>/nodes/<node_key>/devices/<device_id>
GET    /api/diagrams/<diagram_id>/nodes        # 返回 linked_devices
PUT    /api/diagrams/<diagram_id>/content      # 同步节点时清理设备关联
```

节点响应增加：

```json
{
  "node_key": "n3",
  "label": "核心交换机",
  "linked_devices": [
    { "device_id": "d_xxx", "name": "核心交换机", "brand": "华为", "model": "S12700E-8",
      "quantity": 2, "status": "selected", "category": "network" }
  ]
}
```

拓扑画布 `tt` 元数据增加 `devices`，桥接脚本据此画设备角标、渲染属性面板区块；`tt` 仍不写回 `content_json`。

## 6. 实现范围建议

**首版（建议）**

- 设备表 + 设备节点关联表，CRUD、筛选、汇总、CSV 导出。
- 新标签页、编辑弹窗、关联节点选择器。
- 拓扑属性面板设备区块：关联/取消关联/新建并关联；节点角标；设备定位。
- 节点/图纸/设备删除的级联与清理。
- 服务端测试 + 桥接脚本的节点 payload 测试。

**二期（可选）**

- 从拓扑节点批量生成设备（按节点 kind 推断类别、按 `×N` 推断数量）。
- Excel/CSV 导入、列自定义、批量改状态/数量。
- 设备与任务联动（到货/部署任务）、关联视图增加「设备 → 节点」。
- 项目总览增加设备统计卡。
- 全局 AI 助手支持查询/新增设备、从节点生成设备。

## 7. 已确认与二期

已确认：

- 保留「单价 / 小计 / 预估金额」；单价可空，金额只用于方案估算。
- 类别：服务器 / 存储 / 网络 / 安全 / 软件 / 其他；状态：规划中 / 已选型 / 已报价 / 已下单 / 已到货。
- 拓扑联动按原型：关联、取消、从节点新建并关联、设备角标、双向定位；完整字段编辑在设备清单。
- 首版：设备清单 + CSV 导出 + 拓扑节点关联；不含从拓扑批量生成、CSV/Excel 导入、设备↔任务、AI 管理设备。

二期可选：

- 从拓扑节点批量生成设备（按节点 kind 推断类别、按 `×N` 推断数量）。
- Excel/CSV 导入、列自定义、批量改状态/数量。
- 设备与任务联动（到货/部署任务）、关联视图增加「设备 → 节点」。
- 项目总览增加设备统计卡。
- 全局 AI 助手支持查询/新增设备、从节点生成设备。

确认后我再按最终范围改代码。
