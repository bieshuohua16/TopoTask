# 速记浮窗 · 可行性评估与落地记录

> 这份文档是**过程记录**：从「要不要做、怎么做」到「落地时踩了哪些坑」。
> 想知道功能怎么用、接口长什么样，看 **[CAPTURE.md](CAPTURE.md)**。
>
> 适用版本：v1.6（2026-11-26）

## 目录

1. [关键结论](#一关键结论都实测过)
2. [现状盘点](#二现状盘点本仓库)
3. [Demo → 生产：差距清单](#三demo--生产差距清单)
4. [数据模型](#四数据模型)
5. [API](#五api)
6. [桌面壳选型](#六桌面壳选型)
7. [风险登记](#七风险登记)
8. [工作量与分期](#八工作量与分期)
9. [需要拍板](#九需要拍板)
10. [P0 验收标准](#十p0-验收标准)
11. [运行方式](#十一运行方式合并后)
12. [落地状态](#十二落地状态v10)
13. [踩坑](#十三落地时踩到的坑)
14. [v1.2 调整](#十四v12-调整)
15. [收起成标题栏：三个坑](#十五收起成标题栏三个坑)
16. [v1.3：黑框与拖动](#十六v13黑框与拖动)
17. [v1.4：拖动与窗口尺寸](#十七v14拖动与窗口尺寸)
18. [v1.5：速记记的是任务](#十八v15速记记的是任务)
19. [v1.6：进托盘，不进任务栏](#十九v16进托盘不进任务栏)

---

# 速记浮窗并入 TopoTash · 可行性评估

> 评估对象：`docs/prototypes/capture-demo.html`（v0.9）并入 TopoTash 主应用。
> 结论：**可行**。依赖风险已实测排除，主要成本在前端页面和桌面壳，不在数据层。

## 一、关键结论（都实测过）

| 假设 | 验证方式 | 结果 |
|---|---|---|
| Python 3.15 能装 pywebview | 临时 venv 里 `pip install pywebview` | ✅ 6.2.1 |
| pythonnet 有 cp315 轮子 | `pip download pythonnet` | ✅ 3.2.1（`cp311…cp315` 通用轮） |
| WebView2 运行时存在 | 查 `EdgeWebView\Application` | ✅ 158.0.4370.33 |
| Edge 后端能加载 | `import webview.platforms.edgechromium` | ✅ |
| 置顶/无边框/多屏 | `inspect.signature(create_window)` | ✅ `frameless` `on_top` `transparent` `easy_drag` `x/y` `screen` |
| 测试不需要新依赖 | 读 `tests/*` | ✅ 标准库 `unittest` |

## 二、现状盘点（本仓库）

| 层 | 现状 | 位置 |
|---|---|---|
| 数据 | SQLite + WAL；`ensure_schema` **每次启动**执行 `schema.sql`（幂等） | `db.py:119` |
| 迁移 | `migrate_schema` 只处理需要重建表的情况 | `db.py:114` |
| API | Flask 蓝图，错误统一 `{error:{message,code}}` | `api/*.py`、`db.py:141` |
| 前端 | `TT.api` / `TT.esc` / `TT.toast` 现成 | `static/js/api.js` |
| 页面 | `create_app` 里逐个 `@app.get`，模板继承 `base.html` | `app.py:74` |
| 启动器 | 端口探测 + 健康检查 + 单实例复用 | `start_topotash.py` |
| 项目页 | 用 `?tab=` 切 panel，加 tab 是加法 | `templates/project.html:38` |
| 依赖 | 只有 Flask 一个 | `requirements.txt` |

## 三、Demo → 生产：差距清单

| # | Demo 现在 | 生产要改成 | 改动面 |
|---|---|---|---|
| 1 | `localStorage` | 三个 REST 端点 + 一张表 | `schema.sql` `services.py` `api/` |
| 2 | 硬编码 4 个项目 | `GET /api/projects` | `capture.js` |
| 3 | 假 AI（setTimeout） | 先本地补全，接口预留 | `api/ai.py` |
| 4 | 单文件内联 CSS/JS | `capture.css` + `capture.js` + Jinja 模板 | `templates/` `static/` |
| 5 | 浏览器标签页 | pywebview 浮窗 | 新增 `quick_capture.py` |
| 6 | 无热键 | `RegisterHotKey` + 冲突提示 | 同上 |
| 7 | 撤销只在前端 | 服务端删除 + 前端撤销栈 | `api/` |
| 8 | 本地时间字符串 | 存 UTC(Z)，前端转本地 | `services.py` |

## 四、数据模型

```sql
CREATE TABLE IF NOT EXISTS project_updates (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_id     TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    kind        TEXT NOT NULL DEFAULT 'progress'
                CHECK (kind IN ('progress','risk','next','decision')),
    content     TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'floating',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_updates_project
    ON project_updates(project_id, created_at DESC);
```

**只加新表、不改旧表** → 不需要写 `_migrate_*`，`ensure_schema` 启动即生效，老库零风险。

## 五、API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/<id>/updates` | 建一条（`content` 必填，`kind` 默认 progress） |
| GET | `/api/projects/<id>/updates?limit=` | 时间线 |
| DELETE | `/api/updates/<id>` | 撤销 |
| GET | `/api/updates/today` | 胶囊角标「今日 N 条」 |
| POST | `/api/ai/complete` | P2：Tab 补全（不建会话、不落草稿） |

写入时同步 `projects.updated_at`，让首页「最近活跃」排序自动生效。

## 六、桌面壳选型

| 方案 | 依赖 | 置顶 | 无边框 | 结论 |
|---|---|---|---|---|
| **A. pywebview** | +5 个包 | ✅ | ✅ | **推荐**（已实测可装） |
| B. Edge `--app` + Win32 置顶守护 | 0 | ✅ | ❌ 有标题栏 | 降级方案 |
| C. 浏览器独立窗口 | 0 | ❌ | ❌ | 不可行 |

依赖从 1 个变成 6 个（flask / pywebview / pythonnet / clr-loader / proxy_tools / bottle / typing_extensions）。
缓解：`requirements.txt` 保持只装 Flask，浮窗依赖放 `requirements-floating.txt`，代码里 `try/except ImportError` 自动降级到 B。

## 七、风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 公司网络装不了依赖 | 低 | 高 | 已实测可下载；再提供离线 wheel + B 方案 |
| 中文输入法在 frameless+topmost 下异常 | 中 | 高 | 先做 1 天 spike：能输入、能切窗、能粘贴 |
| 全局热键被占用 | 低 | 中 | 可配置 + 注册失败时 toast 提示 |
| 多显示器 / 125% 缩放错位 | 中 | 中 | 存屏幕坐标，启动时校验在可见区域 |
| 双击启动器与浮窗抢实例 | 低 | 中 | 浮窗用独立命名互斥量 |
| 并发写 SQLite | 低 | 低 | WAL 已开；同进程单写 |
| 安全 | 低 | 低 | 只监听 127.0.0.1，不开 0.0.0.0 |

## 八、工作量与分期

| 阶段 | 内容 | 人日 |
|---|---|---|
| **P0** | 浏览器内 `/capture` 页面 + 写库 + 项目页「进展」tab | 1.5–2 |
| **P1** | 桌面壳：pywebview + 热键 + 单实例 + 位置记忆 + 自启 | 1–1.5 |
| **P2** | AI 补全：`/api/ai/complete` + 预取 + 取消 | 1 |
| **P3** | 打磨：多屏、输入法、主题、托盘 | 1 |
| 合计 | | **4.5–5.5** |

**建议顺序**：先做 P0。它不引入任何新依赖，当天就能验证 80% 手感；P1 的壳只有 1 天，风险集中在一个 spike 里。

## 九、需要拍板

1. 接受新增 5 个依赖吗？不接受就走 B 方案（有标题栏）。
2. AI 补全先做本地（历史项目名），还是 P0 就接真模型？
3. 开机自启 / 托盘图标要不要？
4. 「进展」放项目页 tab，还是放概览页的卡片？

## 十、P0 验收标准

- 手动打开 `/capture`，完成「输入 → Enter → 落库 → 时间线可见」；
- 刷新后数据还在；`Ctrl+Z` 能撤销；胶囊角标显示今日条数；
- 单测覆盖：创建 / 列表 / 删除 / 非法 `kind` / 项目不存在；
- 现有 12 个测试文件全绿（`python -m unittest discover tests`）。

## 十一、运行方式（合并后）

### 今天怎么起的

快捷方式 → `python.exe start_topotash.py` → `main()` → 端口探测（`_port_open`）→ 导入 `app` → `flask_app.run(threaded=True)` **阻塞主线程**；浏览器由 daemon 线程 `_open_browser_when_ready` 拉起。

### 合并后：只有一处结构性改动

**主线程从 `flask_app.run()` 换成 `webview.start()`**，Flask 挪到 daemon 线程。

```
pythonw.exe start_topotash.py --floating
├─ 主线程      webview.start()            窗口消息循环（frameless / on_top）
├─ 线程 A      flask_app.run(threaded)    127.0.0.1:5000
└─ 线程 B      RegisterHotKey 消息泵      Ctrl+Alt+N
```

### 冷启动时序

1. 双击 → `main()` 解析参数（`--floating` 默认带 `--no-browser`）
2. 读 `app_settings`：端口、热键、窗口坐标
3. `_port_open(port)` 判断服务在不在
4. 不在 → 起 Flask 线程 → `_wait_health(port, 30s)`
5. `create_window(url=.../capture, frameless=True, on_top=True, x=?, y=?)` → `webview.start()`
6. 注册热键；恢复坐标时校验是否在可见屏幕内，不在就回默认右上角

### 场景表

| 操作 | 结果 |
|---|---|
| 冷启动双击 | 起服务 + 浮窗，胶囊约 1s 出现 |
| 服务在、浮窗在 | 唤起已有窗口（`ShowWindow` + `SetForegroundWindow`），新进程退出 |
| 服务在、浮窗不在（`--no-floating` 起的） | 只建浮窗 |
| 关闭浮窗 | 进程退出，服务随之停止 |
| 浮窗里点「打开主站」 | `webbrowser.open` 到已有端口 |
| 开机自启 | `HKCU\...\Run` → `pythonw ... --floating --no-browser` |

### 控制台窗口

日常用 `pythonw.exe`（无控制台），日志写 `%LOCALAPPDATA%\TopoTash\app.log`（`RotatingFileHandler`）。
调试用 `python.exe start_topotash.py --debug`：有控制台，**只起服务、不起浮窗**（reloader 与 webview 主线程冲突）。

### 为什么热键要独立消息泵

`RegisterHotKey` 的 `WM_HOTKEY` 投递到**注册它的线程**的消息队列，而 pywebview 的消息循环不会转发给我们。所以热键放独立线程：隐藏窗口 + `RegisterHotKey` + `GetMessage` 循环，约 40 行 ctypes。

### 失败与降级

- 端口被非 TopoTash 程序占用 → 复用现有提示，换端口
- WebView2 运行时缺失 → 降级 Edge `--app` + 置顶守护
- 浮窗异常 → 整个进程退出（单进程的代价），重启即可
- 数据库被锁 → 15s 超时后报错（现有行为）

### 改动清单

| 文件 | 改动 |
|---|---|
| `start_topotash.py` | 主线程换成 `webview.start()`；加 `--floating` |
| `quick_capture.py` | 新增：窗口、热键、互斥量、坐标记忆、日志 |
| `setup_first_run.py` | 快捷方式指向 `pythonw` + `--floating`；可选安装浮窗依赖 |
| `requirements-floating.txt` | 新增：`pywebview>=6.2` |
| `README.md` | 「快速开始」补浮窗启动方式与退出方式 |

### 黑窗口怎么消失（pythonw）

今天的快捷方式 `target=sys.executable`（`setup_first_run.py:448`），也就是 `python.exe`——**控制台子系统**，双击必然弹一个常驻黑窗口，关掉窗口 = 停服务。

合并后把 target 换成同目录的 `pythonw.exe`（`Path(sys.executable).with_name("pythonw.exe")`），参数加 `--floating`，黑窗口就不再出现，任务管理器里只有一个 `pythonw.exe`。

代价与对应处理：

| 代价 | 现象 | 处理 |
|---|---|---|
| `sys.stdout/stderr` 是 `None` | 任何 `print()` 直接抛 `AttributeError` | 启动第一步把 stdout/stderr 重定向到 `%LOCALAPPDATA%\TopoTash\app.log` |
| `sys.stdin` 是 `None` | `_fail()` 里的 `input()` 抛异常 | 无控制台时改用 `MessageBoxW` 弹窗 |
| 没有 Ctrl+C | 停不了服务 | 退出走浮窗 `×` 或托盘菜单 |
| 错误不可见 | 崩了不知道为什么 | `RotatingFileHandler` + `sys.excepthook` / `threading.excepthook` 写日志 |

三种启动方式的分工：

| 场景 | 命令 | 有没有窗口 |
|---|---|---|
| 日常 | 快捷方式 → `pythonw … --floating` | 无 |
| 调试 | `python start_topotash.py --debug` | 有（只起服务） |
| 只要浏览器 | `python start_topotash.py` | 有（Flask 在主线程） |

`首次启动.bat` 仍然保留 cmd 窗口——它是一次性安装向导，需要交互与回显，装完就不用再碰。


## 十二、落地状态（v1.0）

| 项 | 状态 | 位置 |
|---|---|---|
| `project_updates` 表 + 索引 | ✅ | `schema.sql` §19 |
| 服务层读写 | ✅ | `services.py`（`create_update_record` 等 7 个函数） |
| 4 个 API | ✅ | `api/updates.py` |
| 项目页「进展」tab + 时间线 | ✅ | `templates/project.html`、`static/js/project.js`、`static/css/topotash.css` |
| `/capture` 页面（语法 / `@` / `#` / 新建 / 撤销 / 草稿） | ✅ | `templates/capture.html`、`static/js/capture.js`、`static/css/capture.css` |
| 浮窗壳 + 热键 + 单实例 + 位置记忆 | ✅ | `quick_capture.py`、`start_topotash.py --floating` |
| 测试 | ✅ 17 个新用例 | `tests/test_api_updates.py` |
| P2 AI 补全 | ⏳ 未做 | Tab 目前只做本地补全 |

**已知取舍**：`#` 是类型选择器（不是标签）；`project_updates` 没有标签表，以后要标签再加 `update_tags`。


## 十三、落地时踩到的坑

### 1. 不要用 pywebview 的 `js_api`

`window.pywebview.api.*` 在 WebView2 + WinForms 下会跨线程访问 COM：

```
[pywebview] Error ... CoreWebView2Controller members can only be accessed from the UI thread
[pywebview] Error ... maximum recursion depth exceeded
```

后果不是报个错，而是 **Python 主线程递归卡死 → 整个本地服务不再响应**（`/healthz` 超时、页面永远「加载中」）。

改法：浮窗加载 `/capture?shell=1`，窗口按钮 POST `/api/capture/window`，
Python 侧用 ctypes 的 `FindWindowW` / `ShowWindow` / `PostMessageW` 操作窗口，
开机自启走 `winreg`。这些任一线程调用都安全。

### 2. 中文输入法会吃掉 Tab

Tab 是拼音输入法的「下一候选」，组合状态下页面收不到 Tab（`isComposing=true`）。
所以选择器的主确认键是 **Enter**，Tab 只作别名；提示文案改成 `Enter 记录 · @ 换项目 · # 类型`。

### 3. `.progress` 全局类名冲突

类型 `progress` 和进度条 `.progress` 撞名，时间线第二行被压成 16px。类型类名统一加 `upd-` 前缀。

### 4. `TEMPLATES_AUTO_RELOAD`

Flask 默认配置里 `TEMPLATES_AUTO_RELOAD=None`，`setdefault` 不会覆盖，必须直接赋值。


## 十四、v1.2 调整

| 反馈 | 处理 |
|---|---|
| 标题/logo 跟主站不一致 | 页面标题与原生窗口标题统一 `TopoTash 速记`；logo 复用主站 `base.html` 的节点网络标 |
| 最小化应该是「收起成标题栏」而不是进任务栏 | `－` → `SetWindowPos` 把窗口改成 260×44 的悬浮标题栏（右上角不动），点标题栏 `SetWindowPos` 还原；热键改为收起/展开切换，页面每 800ms 轮询 `/api/capture/state` 同步 |
| Tab 不顺手 | 删除 Tab 补全与「这句更像任务」建议条；选择器确认键统一为 Enter |
| `@` 选完项目要看到待办 | 面板新增「待办」区块：`GET /api/tasks?project_id=`，显示未完成前 3 条（优先级圆点 + 截止日） |

另外修了一个 CSS 坑：`.cap-winbtns` 的 `display:flex` 覆盖了 `[hidden]` 的 UA 样式，
导致浏览器模式也显示窗口按钮；补了全局 `[hidden]{display:none!important}`。

## 十五、收起成标题栏：三个坑

1. **ctypes 64 位句柄截断（最隐蔽）**
   不声明 `argtypes` 时，ctypes 把 Python int 当 32 位 C int 传，`HANDLE` 被截断：
   `SetWindowPos` 返回 0、`GetLastError()=1400`（`ERROR_INVALID_WINDOW_HANDLE`），
   但窗口纹丝不动，日志里也只有一行失败。必须给
   `SetWindowPos / GetWindowRect / EnumWindows / GetWindowTextW / ShowWindow / PostMessageW`
   全部声明 `argtypes` + `restype`。

2. **`FindWindowW(None, 标题)` 会误伤浏览器**
   浏览器里开着 `/capture` 标签页时，窗口标题同样是「TopoTash 速记」，
   按标题找窗可能抓到浏览器，去改别人的窗口。
   改成 `EnumWindows` + 进程 id 匹配（只认本进程的窗口）。

3. **DPI 缩放**
   `260×44` 是逻辑像素；125% / 150% 缩放下要乘 `GetDpiForWindow()/96`，
   否则标题栏内容会被挤扁。

另外 `min_size=(360, 460)` 会卡住收起，已改成 `(220, 40)`。

回归测试用**屏幕外的 Tk 窗口**（真实 Win32 句柄，不打扰桌面）：
`tests/test_capture_window.py` 覆盖「找到本进程窗口 / 收起尺寸 / 右边缘不动 / 还原」。

## 十六、v1.3：黑框与拖动

### 黑框
收起后窗口是 260×44，但页面背景是深色渐变，圆角（22px）处漏出深色，看起来像黑框。
→ `body.is-collapsed { background: #fff; }`，标题栏与背景同色，黑边消失。

### 拖动为什么完全没反应
`easy_drag=True` 时 pywebview 注入的拖拽脚本会调 `window.move()`，
在 Python 3.15 + pywebview 6.2.1 上 `winforms.py:635` 的 `SetWindowPos` 收到 `None`：

```
ctypes.ArgumentError: argument 5: TypeError: 'NoneType' object cannot be interpreted as an integer
[pywebview] Exception occurred during on_script_notify
```

异常被 pywebview 吞掉只打日志，窗口纹丝不动。
→ 关掉 `easy_drag`，改用 Win32 的 `ReleaseCapture()` + `SendMessageW(WM_NCLBUTTONDOWN, HTCAPTION)`：

- `mousedown` 后移动超过 6px 才发一次 `POST /api/capture/window {action:'drag'}`
  （请求会阻塞到松手，属于预期；本地线程池不受影响）
- 没有移动就是点击 → 胶囊点击展开
- 标题栏里的按钮/输入框通过 `IGNORE_DRAG` 选择器排除，不参与拖动

## 十七、v1.4：拖动与窗口尺寸

### 拖动：别用模态拖拽循环

上一版用 `WM_NCLBUTTONDOWN + HTCAPTION` 让 Windows 接管拖动，在 WebView2 下仍然拖不动
（模态循环会吞掉后续消息，点击也跟着坏）。改成**完全可控的移动**：

- `mousedown` 起点（`screenX/screenY`）+ 轮询缓存里拿窗口当前 `x/y`
- `mousemove` 位移 > 5px 才开始算拖动，16ms 节流发一次
  `POST /api/capture/window {action:'move', x, y}` → `SetWindowPos(SWP_NOSIZE)`
- 没移动 = 点击（胶囊点击展开）
- 位移要乘 `devicePixelRatio`（`screenX` 是 CSS 像素，窗口坐标是物理像素）

### 窗口被存成「条状」导致右上角按钮被裁

收起时关掉窗口，`save_geometry()` 会把 260×44 的 pill 尺寸写进 `window.json`；
下次启动就按 260 宽开窗，标题栏内容放不下，`⚙ ×` 被裁掉。

修法：

- 收起状态下保存**展开尺寸**（`_state['expanded']`）
- 启动/展开时把尺寸 clamp 到 `MIN_EXPANDED = (380, 520)`
- 窄窗口兜底：`@media (max-width: 399px)` 隐藏「今日 N 条」，优先保住右侧按钮

## 十八、v1.5：速记记的是任务

需求变更：速记不再写「进展」，而是直接建**任务**。

| 变化 | 处理 |
|---|---|
| 删除项目页「进展」tab | `templates/project.html`、`static/js/project.js`、`static/css/topotash.css` 里的 `.upd-*` 全部移除 |
| `#` 从「类型」改成「售前阶段」 | 选择器列 需求调研 / 方案编写 / POC 验证 / 招投标，写入 `tasks.stage` |
| 速记写任务 | `POST /api/tasks`（title + stage + `source=floating`），待办列表自动刷新 |
| 删除 `project_updates` 表与 API | `schema.sql` / `services.py` / `api/updates.py` 整块移除；老库保留空表不影响 |
| 「工作台」入口上移 | 从设置浮层挪到标题栏 `＋ 新建` 旁边，`target=_blank` 走系统浏览器 |
| `@` 选项目后待办不刷新 | `setProject()` 里直接 `await loadTasks()`，不再依赖已被删除的最近记录 |

测试：`test_api_updates.py` 拆成 `test_capture_page.py`（页面 + 浮窗端点 + 「速记=建任务」契约）+ 两个窗口几何测试。

## 十九、v1.6：进托盘，不进任务栏

| 需求 | 实现 |
|---|---|
| 程序不要占任务栏 | `hide_from_taskbar()` 给窗口加 `WS_EX_TOOLWINDOW` 并清掉 `WS_EX_APPWINDOW`，再 `SetWindowPos(SWP_FRAMECHANGED)`；任务栏和 Alt+Tab 都不再出现 |
| 右下角托盘图标 | `tray_icon.py`：独立线程里建消息窗口（`HWND_MESSAGE`）+ `Shell_NotifyIconW(NIM_ADD)` + `GetMessage` 循环 |
| 托盘菜单 | 右键 `TrackPopupMenu`：展开 / 收起、打开工作台、退出；左键单击 = 显示/隐藏 |
| `×` 的语义 | 从「退出」改成「收进托盘」（`SW_HIDE`），退出走托盘菜单 |
| 热键 | `Ctrl+Alt+N` = 隐藏→显示、收起→展开、其他情况收进托盘 |

三个坑：

1. **`ShowWindow` 返回的是「之前的可见状态」**，拿它当成功标志会误判——显示一个隐藏窗口时返回 0，接口直接 404。改成 `ShowWindow` 后查 `IsWindowVisible`。
2. **`_hwnd()` 原来要求 `IsWindowVisible`**，窗口一藏进托盘就找不到自己了，收起/展开全 404。改成枚举所有同名窗口、优先返回可见的。
3. **单实例互斥 + 隐藏窗口**：窗口隐藏后 `MainWindowTitle` 为空，按标题杀进程会漏杀，新实例被互斥挡回。调试/重启时要按 PID 杀。

托盘图标注册是否成功，用 `NIM_MODIFY` 二次确认（图标不存在时它返回 FALSE），日志里会打「图标已注册：True」。

### 补记：托盘「打开工作台」失效

根因很低级：`quick_capture.py` 里用了 `webbrowser` 但没 `import`，
异常被 ctypes 的回调层吞成一行 `Exception ignored while calling ctypes callback function ...`，
菜单点了没反应、日志里也只是噪音。

修法：

- 补 `import webbrowser`，抽出 `workbench_url()` / `open_workbench()`（可单测），
  `webbrowser.open()` 返回 False 时用 `os.startfile()` 兜底
- 托盘三个动作统一包一层 `_safe_action()`，异常打成 `[速记] 托盘动作失败：...`，不再静默
- 托盘窗口从 `HWND_MESSAGE` 换成隐藏的 `WS_POPUP`，`FindWindowW("TopoTashTrayWnd", ...)` 能找到，
  调试时可以直接 `PostMessage(WM_TRAYICON, WM_RBUTTONUP)` 把菜单弹出来点

实测：菜单弹出后点「打开工作台」，Chrome 切到 `项目总览 · TopoTash 拓事`，日志无异常。
