# docs 索引

| 文档 | 内容 |
|---|---|
| [CAPTURE.md](CAPTURE.md) | **桌面速记浮窗**：交互速查、记录落点、窗口/托盘行为、接口、排错、测试 |
| [feasibility-capture.md](feasibility-capture.md) | 速记的可行性评估与落地记录（设计决策、分期、19 条踩坑） |
| [DESIGN.md](DESIGN.md) | 数据模型、Schema、API、前端架构 |
| [API.md](API.md) | REST API 明细 |
| [DESIGN-TEAM.md](DESIGN-TEAM.md) | 多用户 / 团队 / 权限设计 + 宝塔部署方案 |
| [prototypes/](prototypes/) | 速记设计原型：10 张设计图 + 历史 demo + `archive/` 单页原型 |
| [screenshots/](screenshots/) | 当前界面的真实截图（README 与文档引用） |
| `ui-prototype.html` | 四套主题、七个页面的静态 UI 原型（更早的整体设计稿） |

## 速记相关代码

| 文件 | 作用 |
|---|---|
| `templates/capture.html` | 浮窗页面结构 |
| `static/js/capture.js` | 输入、`@`/`#` 选择器、提交、拖动、收起 |
| `static/css/capture.css` | 浮窗样式（收起态、窄窗兜底） |
| `api/capture.py` | 窗口动作（收起/展开/移动/隐藏）、托盘状态、开机自启 |
| `quick_capture.py` | pywebview 壳、全局热键、单实例、托盘启动、位置记忆 |
| `tray_icon.py` | 托盘图标 + 任务栏隐藏（纯 ctypes，无第三方依赖） |
| `start_topotash.py` | `--floating` 入口 |
| `tests/test_capture_*.py`、`tests/test_tray.py`、`tests/test_workbench.py` | 对应测试 |
