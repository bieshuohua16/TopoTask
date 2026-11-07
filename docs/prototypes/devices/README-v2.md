# 设备清单迭代 · 型号角标 / 模板库

> 状态：**已实现（2026-11）**。本目录保留确认用原型；实际界面见：
> [12-template-library.png](../../screenshots/12-template-library.png)、
> [15-topology-device-panel.png](../../screenshots/15-topology-device-panel.png)、
> [16-actual-device-modal-blank.png](../../screenshots/16-actual-device-modal-blank.png)、
> [20-actual-template-edit.png](../../screenshots/20-actual-template-edit.png)、
> [19-actual-template-preview.png](../../screenshots/19-actual-template-preview.png)。
> 实际实现与原型的小差异：顶部模板选择使用原生可搜索下拉；模板库/导入弹窗按现有组件风格落地。

## 1. 拓扑节点角标：显示型号，而不是「设备 ×N」

原型：[06-model-labels.png](06-model-labels.png)

规则：

- 优先显示设备的 `model`（型号）；型号为空时显示设备 `name`。
- 不再显示 `设备 ×N`，也不在角标上显示数量；数量在属性面板/设备清单中查看。
- 一个节点关联多个设备时，角标**纵向排列**（原型中核心交换机展示了 2 个型号）。
- 型号过长时截断显示（建议最多 18–20 个字符，完整值放在 `title` 和属性面板）。

已确认：多设备最多显示 2 个型号 + `+N`；完整列表在属性面板，避免遮挡画布。

## 2. 新增设备弹窗：删除三个灰色占位提示

原型：[08-template-blank.png](08-template-blank.png)

- 删除「设备名称」「品牌」「型号」以及同一弹窗内规格、单价、备注的示例 `placeholder`；不再用灰色文案提示。
- 模板搜索框的「搜索模板…」属于功能提示，保留。

## 3. 全局设备模板库

原型：

- 模板库页面：[09-template-library.png](09-template-library.png)
- 新增 / 编辑模板：[11-template-edit.png](11-template-edit.png)
- CSV 导入弹窗：[10-template-import.png](10-template-import.png)
- 从模板新增设备：[07-template-picked.png](07-template-picked.png)

### 3.1 入口与定位

- 全局页面 `/device-templates`，左侧导航「设备模板」，不绑定项目。
- 模板是**预设**：创建项目设备时复制字段到项目设备，之后修改项目设备不影响模板。
- 设备清单的「新增设备」弹窗顶部增加「从设备模板开始」；可选择模板或完全空白新建。

### 3.2 模板字段

建议模板只保存可复用的技术/商务信息，不保存项目和数量：

- 类别、品牌、型号、关键参数、默认单位、参考单价、备注。
- 不要求设备名称；新建模板默认类别为服务器。
- 不包含：项目、数量、项目状态、供应商/负责人（这些是项目级信息，可在带出后填写）。
已确认：模板只带技术字段 + 参考价，不带数量、供应商/负责人；数量和供应商在项目设备里填写。

### 3.3 模板库页面

- 摘要：模板数量、覆盖类别、覆盖品牌。
- 筛选：搜索（名称/品牌/型号/参数）、类别、品牌。
- 表格：设备/型号、类别、品牌、关键参数、默认单位、参考单价、更新时间、编辑/删除。
- 操作：下载 CSV 模板、导入 CSV、新增模板。
- 行编辑打开模板表单；删除需确认。

### 3.4 CSV 导入

- 支持 UTF-8 / UTF-8 BOM，第一行表头。
- 列：`类别,品牌,型号,关键参数,单位,参考单价,备注`。
- 类别可写中文（服务器/存储/网络/安全/软件/其他）或英文 key。
- 先预览再导入：显示可导入/重复/错误行数，重复项默认跳过，可切换覆盖更新。
- 重复判定：品牌 + 型号。
- 导入失败行给出原因，不影响其它行。

### 3.5 新增设备时的模板选择

- 新增设备弹窗顶部：模板搜索/选择 + 「管理模板」入口。
- 选中后带入品牌、型号、类别、参数、单位、参考价；项目设备名称自动取型号（可修改），数量默认 1，关联节点为空。
- 可随时「更换」「清空」，清空后就是空白新建。
- 编辑已有设备时不显示模板选择，避免误覆盖；如需「用模板重置」，后续再加。

已确认：拓扑属性面板加一个紧凑的模板下拉，选中后带入技术字段；节点数量仍按当前节点填写。

### 3.6 数据模型与 API 草案

```sql
CREATE TABLE device_templates (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,           -- 内部隐藏显示名，兼容旧数据；UI 不要求填写
  category    TEXT NOT NULL DEFAULT 'server',
  brand       TEXT NOT NULL DEFAULT '',
  model       TEXT NOT NULL DEFAULT '',
  spec        TEXT NOT NULL DEFAULT '',
  unit        TEXT NOT NULL DEFAULT '台',
  unit_price  REAL,
  note        TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
```

```
GET    /api/device-templates?category=&q=
POST   /api/device-templates
PATCH  /api/device-templates/<id>
DELETE /api/device-templates/<id>
POST   /api/device-templates/import/preview   # CSV 解析预览
POST   /api/device-templates/import           # 正式导入
GET    /api/device-templates/sample.csv       # 下载标准模板
```

模板全局共享；设备创建/编辑接口保持现有 `devices` 结构，不把模板 id 存进设备（复制字段，避免模板变更影响历史项目）。

## 4. 已确认

1. 多设备节点：最多 2 个型号 + `+N`。
2. 模板不带默认数量、供应商/负责人。
3. CSV 重复项默认跳过，可切换覆盖更新。
4. 拓扑内「新建并关联」提供紧凑模板下拉。
5. 模板页入口为左侧「设备模板」。
6. 型号过长截断 + 悬浮显示完整值；导入弹窗提供「下载标准 CSV 模板」。
7. 模板不再要求设备名称，按品牌+型号识别；新建模板默认类别为服务器。
