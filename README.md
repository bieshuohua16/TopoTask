# TopoTash 拓事

> 面向 IT 售前工程师的项目工作台：**项目 → 任务 → 拓扑图** 放在同一条线上。

TopoTash 是一个自带后端的完整 Web 应用。每个项目下有多个任务和多张拓扑图；任务可以关联图纸，拓扑图节点可以标记「待跟进」并直接创建或跳转到任务；所有视图都可以按售前阶段聚合。

- 项目总览、阶段看板、拓扑图库、项目工作台
- 任务台：列表 / 看板、优先级、子任务、标签、循环任务、搜索、AI 助手
- 拓扑编辑器：系统架构图、逻辑拓扑、POC 部署图，节点级任务联动
- SQLite 持久化，数据全部落在项目根目录，离线可用

![项目总览](docs/screenshots/01-dashboard.png)

## 界面预览

| 阶段看板 | 项目工作台（任务） |
|---|---|
| ![阶段看板](docs/screenshots/02-board.png) | ![任务台](docs/screenshots/04-project-tasks.png) |

| 拓扑编辑器（节点跟进） | 关联视图 |
|---|---|
| ![拓扑编辑器](docs/screenshots/06-editor.png) | ![关联视图](docs/screenshots/07-links.png) |

## 快速开始

环境：Python 3.10+（开发时使用 3.15），浏览器用 Chrome / Edge。

```bash
# 1. 安装依赖（只有一个 Flask）
python -m pip install flask

# 2. 初始化数据库（生成 topotash.db；首次启动也会自动创建）
python app.py init-db

# 3. 可选：写入 4 个示例项目 / 23 个任务 / 4 张拓扑图
python app.py seed-demo

# 4. 启动（debug，127.0.0.1:5000）
python app.py
```

打开 <http://127.0.0.1:5000>。数据库默认在 `./topotash.db`，可用 `TOPOTASH_DB` 环境变量覆盖。

> 本应用没有登录与权限控制，默认只监听 `127.0.0.1`，请勿直接暴露到公网。

## 功能地图

| 页面 | 路径 | 说明 |
|---|---|---|
| 项目总览 | `/` | 项目卡片、阶段筛选、统计、即将到期、节点待跟进 |
| 阶段看板 | `/board` | 四个售前阶段泳道，任务卡片可点击直达任务台 |
| 拓扑图库 | `/diagrams` | 全部项目的拓扑图，显示节点数 / 关联任务 / 待跟进数 |
| 项目工作台 | `/projects/<id>` | 概览 / 任务 / 拓扑图 / 关联视图 四个标签页 |
| 拓扑编辑器 | `/projects/<id>/diagrams/<did>` | 全屏画布，自动保存到 SQLite |

## 架构说明

TopoTash 由一个 Flask 应用统一托管：

- **Shell**：Jinja 页面骨架 + 原生 JS，负责项目导航、总览、阶段看板与项目工作台。
- **内置任务台**：自包含的单文件前端模块，通过桥接脚本接入项目级 API，保留完整交互。
- **内置拓扑编辑器**：自包含的 SVG 编辑器，通过桥接脚本保存画布 JSON，并在属性面板与节点上提供任务联动。
- **桥接层**：同源 `fetch` 调用 REST API，`postMessage` 在 iframe 与父页面之间传递保存状态、任务跳转等事件。
- **数据层**：Flask + sqlite3 标准库，无 ORM；`schema.sql` 是唯一建表来源。

任务台与拓扑编辑器都是原生 JS、零框架依赖，不需要 Vue/React 适配层，也没有前端构建步骤。

## 目录结构

```
TopoTash/
├── app.py                      # Flask 入口、页面路由、CLI（init-db / seed-demo）
├── db.py                       # SQLite 连接、事务、通用工具
├── schema.sql                  # 全部建表语句（含索引、外键、CHECK）
├── services.py                 # 领域服务：序列化、任务/节点同步、任务台状态
├── topotash.db                 # 运行时数据库（init-db 生成）
├── api/
│   ├── __init__.py
│   ├── projects.py             # 项目 + 任务台全量状态同步
│   ├── tasks.py                # 任务、子任务、标签、任务↔拓扑图
│   ├── diagrams.py             # 图纸内容、节点索引、节点跟进/关联
│   └── views.py                # 总览、阶段看板、关联视图、全局搜索
├── templates/                  # Jinja 页面骨架
│   ├── base.html
│   ├── dashboard.html
│   ├── board.html
│   ├── diagrams.html
│   ├── project.html
│   └── editor.html
├── static/
│   ├── css/topotash.css
│   ├── js/                     # shell / dashboard / board / project / editor
│   └── apps/                   # 内置任务台、内置拓扑编辑器与桥接脚本
├── tools/
│   ├── seed_demo.py            # 示例数据
│   └── migrate_json.py         # 历史 JSON 数据导入
├── docs/
│   ├── DESIGN.md               # 数据模型、Schema、API、前端架构
│   ├── API.md                  # REST API 明细
│   └── screenshots/
├── licenses/
│   └── THIRD_PARTY_NOTICES.md  # 第三方组件与许可
├── .gitignore
├── README.md
└── requirements.txt
```

## 历史数据导入

如果手头已有旧版任务 JSON 或画布 JSON，可以用迁移脚本导入：

```bash
# 导入任务 JSON 为一个 TopoTash 项目（原「项目分类」变任务分类）
python tools/migrate_json.py --todo data/todos.json --project-name "历史任务迁移"

# 每个旧分类拆成一个项目
python tools/migrate_json.py --todo data/todos.json --split-projects

# 同时导入目录下的画布 JSON（默认挂到第一个项目）
python tools/migrate_json.py --todo data/todos.json --visio data/diagrams

# 指定数据库 / 目标项目 / 阶段
python tools/migrate_json.py --todo todos.json --db my.db \
  --project-name "XX 银行" --stage poc --visio-project "XX 银行"
```

迁移脚本会保留任务 id、创建时间、子任务、标签、循环规则、AI 配置与对话记录；画布 JSON 会解析出节点索引，但不会自动建立节点-任务关联。

## 主要接口

完整说明见 [docs/API.md](docs/API.md)。

```
GET    /api/projects                         项目列表（含统计）
POST   /api/projects                         新建项目
GET    /api/projects/<id>                     项目详情（任务/拓扑/动态）
GET    /api/projects/<id>/todo-state          任务台全量状态
PUT    /api/projects/<id>/todo-state          任务台全量回写（桥接用）

GET    /api/tasks?project_id=&stage=&status=  任务查询
POST   /api/tasks                             新建任务
PATCH  /api/tasks/<id>                        更新任务
POST   /api/tasks/<id>/diagrams               任务关联拓扑图
DELETE /api/tasks/<id>/diagrams/<did>         取消关联

GET    /api/diagrams?project_id=              拓扑图列表
POST   /api/diagrams                          新建拓扑图
GET    /api/diagrams/<id>/content             画布 JSON（含节点跟进信息）
PUT    /api/diagrams/<id>/content             保存画布 JSON（同步节点索引）
POST   /api/diagrams/<id>/nodes/<key>/followup 标记节点 / 创建或关联任务
DELETE /api/diagrams/<id>/nodes/<key>/links/<task_id> 取消节点任务关联

GET    /api/views/overview                    总览聚合
GET    /api/views/stage-board                 阶段看板
GET    /api/views/links                       任务↔图 / 节点↔任务
GET    /api/views/search?q=                   全局搜索
```

## 设计说明

- 技术选型：Flask 3 + sqlite3 标准库 + Jinja + 原生 JS，无 ORM、无前端构建步骤，便于本地运行和二次修改。
- 项目是唯一枢纽：任务与拓扑图都必须挂在项目下，跨项目查询由聚合接口完成。
- 节点索引：`diagram_nodes` 不是画布副本，而是从 `content_json` 解析出的「可检索节点」，保存画布时增量 upsert、删除已不存在的节点。
- 节点角标状态：`diagram_nodes.followup_status` 与主任务状态联动；任务完成时自动把角标改成「已完成」。
- 自动保存：拓扑编辑器每次 `commit()` 后 900ms 防抖 PUT；任务台每次 `saveStore()` 后 650ms 全量 PUT。数据量是个人/小团队级别，全量同步比做增量 diff 更稳。

## 已知限制

- 单用户本地应用，没有认证 / 多租户 / 冲突合并；同一个项目不要同时在两个浏览器里编辑。
- 拓扑图缩略图暂用占位图，未生成真实 PNG 预览。
- 任务台的 AI 助手由浏览器直连 OpenAI 兼容服务，Key 存在项目 `todo_config` 中，不经过 Flask。
- 删除项目会级联删除任务、拓扑图与关联，界面有二次确认。

## 许可

内置拓扑编辑器包含 ELK.js（EPL-2.0）、web-worker（Apache-2.0）、Affinity 图标集（The Unlicense）等第三方组件，许可与版权声明见 [licenses/THIRD_PARTY_NOTICES.md](licenses/THIRD_PARTY_NOTICES.md)。
