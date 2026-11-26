"""TopoTash 速记浮窗（pywebview 桌面壳）。

两种用法：

    python start_topotash.py --floating     # 服务 + 浮窗（推荐）
    python quick_capture.py --port 5000     # 只开浮窗，连已在跑的服务

浮窗特性：无边框、始终置顶、全局热键 Ctrl+Alt+N 显示/隐藏、位置记忆、
单实例（重复启动只唤起已有窗口）。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
import urllib.request
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 5000
WINDOW_TITLE = "TopoTash 速记"
MUTEX_NAME = "Global\\TopoTashCapture"
DEFAULT_SIZE = (420, 620)
MIN_SIZE = (360, 460)
PILL_SIZE = (260, 44)
MIN_EXPANDED = (380, 520)
HOTKEY_LABEL = "Ctrl+Alt+N"
WM_HOTKEY = 0x0312
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "TopoTashCapture"

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ---------------------------------------------------------------------------
# 路径与日志
# ---------------------------------------------------------------------------
def app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / "TopoTash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return app_dir() / "app.log"


def redirect_streams() -> None:
    """pythonw.exe 下 sys.stdout/stderr 是 None，任何 print 都会炸；先重定向到日志。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = open(log_path(), "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


# ---------------------------------------------------------------------------
# 服务探测
# ---------------------------------------------------------------------------
def health_ok(port: int, timeout: float = 1.5) -> bool:
    try:
        with _OPENER.open(f"http://{HOST}:{port}/healthz", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")).get("ok") is True
    except Exception:
        return False


def port_open(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=0.6):
            return True
    except OSError:
        return False


def wait_health(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if health_ok(port):
            return True
        time.sleep(0.25)
    return False


# ---------------------------------------------------------------------------
# 单实例
# ---------------------------------------------------------------------------
def acquire_mutex():
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return handle, kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def activate_existing() -> bool:
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


# ---------------------------------------------------------------------------
# 窗口位置
# ---------------------------------------------------------------------------
def geometry_path() -> Path:
    return app_dir() / "window.json"


def load_geometry():
    try:
        data = json.loads(geometry_path().read_text(encoding="utf-8"))
        width = int(data.get("width") or DEFAULT_SIZE[0])
        height = int(data.get("height") or DEFAULT_SIZE[1])
        return width, height, data.get("x"), data.get("y")
    except Exception:
        return DEFAULT_SIZE[0], DEFAULT_SIZE[1], None, None


def save_geometry(window) -> None:
    if _state["collapsed"] and _state["expanded"]:
        x, y, width, height = _state["expanded"]
    else:
        try:
            x, y = window.x, window.y
            width, height = window.width, window.height
        except Exception:
            return
    if x is None or y is None or not width or not height:
        return
    try:
        geometry_path().write_text(
            json.dumps(
                {"x": int(x), "y": int(y), "width": int(width), "height": int(height)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover - 磁盘只读等
        print(f"[速记] 保存窗口位置失败：{exc}", flush=True)


def bind_geometry(window) -> None:
    """窗口移动 / 缩放 / 关闭时记位置，避免销毁后再取坐标。"""
    def remember(*_args):
        save_geometry(window)

    for name in ("moved", "resized", "closing"):
        try:
            event = getattr(window.events, name)
            event += remember
        except Exception:
            continue


def clamp_to_screens(x, y, width: int, height: int):
    """多显示器 / 分辨率变化后，别让窗口落在看不见的地方；顺带保证最小展开尺寸。"""
    try:
        user32 = ctypes.windll.user32
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)   # 虚拟屏幕左上角
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)   # 虚拟屏幕尺寸
    except Exception:
        return x, y
    width = max(int(width), MIN_EXPANDED[0])
    height = max(int(height), MIN_EXPANDED[1])
    if x is None or y is None or not (vx - width + 80 <= x <= vx + vw - 80) or not (vy <= y <= vy + vh - 80):
        x = vx + vw - width - 40
        y = vy + 40
    return int(x), int(y), width, height


# ---------------------------------------------------------------------------
# 收起成标题栏（不是最小化到任务栏）
# ---------------------------------------------------------------------------
HWND_TOPMOST = -1
SWP_SHOWWINDOW = 0x0040
_state = {"collapsed": False, "expanded": None}


def _configure_win32() -> None:
    """声明 argtypes/restype。

    ctypes 默认把 Python int 按 32 位 C int 传，窗口句柄在 64 位下会被截断，
    SetWindowPos 会返回 ERROR_INVALID_WINDOW_HANDLE(1400) 却看不出原因。
    """
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


_configure_win32()


def _hwnd() -> int:
    """只认本进程的窗口。

    直接 FindWindowW(None, 标题) 会误伤标题相同的其他窗口
    （比如浏览器里打开着 /capture 的标签页），结果去改别人的窗口。
    """
    if os.name != "nt":
        return 0
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid = kernel32.GetCurrentProcessId()
    found = []

    def _callback(hwnd, _lparam):
        try:
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value != pid:
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value == WINDOW_TITLE:
                found.append(hwnd)
                return False
        except Exception:
            pass
        return True

    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_callback)
    try:
        user32.EnumWindows(callback, 0)
    except Exception:
        return 0
    if not found:
        return 0
    # 优先返回可见窗口（隐藏到托盘后仍能找到）
    visible = [h for h in found if user32.IsWindowVisible(h)]
    return visible[0] if visible else found[0]


def _rect(hwnd):
    rect = _RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def _dpi_scale(hwnd) -> float:
    """125% / 150% 缩放时，260×44 是逻辑像素，要按 DPI 放大成物理像素。"""
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(wintypes.HWND(hwnd))
        return (dpi / 96.0) if dpi else 1.0
    except Exception:
        return 1.0


def pill_size(hwnd) -> tuple[int, int]:
    scale = _dpi_scale(hwnd)
    return (round(PILL_SIZE[0] * scale), round(PILL_SIZE[1] * scale))


SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004


def _place(hwnd, x, y, width, height, flags=SWP_SHOWWINDOW) -> bool:
    ok = ctypes.windll.user32.SetWindowPos(
        hwnd, HWND_TOPMOST, int(x), int(y), int(width), int(height), int(flags)
    )
    if not ok:
        print(f"[速记] 调整窗口失败（err={ctypes.windll.kernel32.GetLastError()}）", flush=True)
    return bool(ok)


def collapse() -> bool:
    """收起成 260×44 的悬浮标题栏，右上角不动。"""
    hwnd = _hwnd()
    if not hwnd:
        return False
    x, y, width, height = _rect(hwnd)
    if not _state["collapsed"]:
        _state["expanded"] = (x, y, width, height)
    right = x + width
    pill_w, pill_h = pill_size(hwnd)
    ok = _place(hwnd, right - pill_w, y, pill_w, pill_h)
    _state["collapsed"] = ok
    return ok


def expand() -> bool:
    hwnd = _hwnd()
    if not hwnd:
        return False
    x, y, width, height = _rect(hwnd)
    if _state["expanded"]:
        ex, ey, ew, eh = _state["expanded"]
        x, y, width, height = ex, ey, ew, eh
    width = max(int(width), MIN_EXPANDED[0])
    height = max(int(height), MIN_EXPANDED[1])
    right = x + width
    ok = _place(hwnd, right - width, y, width, height)
    _state["collapsed"] = not ok
    return ok


def toggle_collapsed() -> bool:
    return expand() if _state["collapsed"] else collapse()


def is_collapsed() -> bool:
    return bool(_state["collapsed"])


def move_to(x: int, y: int) -> bool:
    """把窗口移到 (x, y)，尺寸不变。

    不用 WM_NCLBUTTONDOWN 的模态拖拽循环（WebView2 下会吞消息、点击也跟着坏），
    改成前端每次 mousemove 发一次，请求线程立刻返回。
    """
    hwnd = _hwnd()
    if not hwnd:
        return False
    _, _, width, height = _rect(hwnd)
    ok = _place(hwnd, int(x), int(y), width, height, SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
    if ok:
        _state["expanded"] = (int(x), int(y), width, height)
    return ok


def window_rect() -> tuple[int, int, int, int]:
    hwnd = _hwnd()
    if not hwnd:
        return (0, 0, 0, 0)
    return _rect(hwnd)


_tray = {"obj": None}


def tray_ready() -> bool:
    tray = _tray["obj"]
    return bool(tray and tray.hwnd and not tray.error)


def is_hidden() -> bool:
    hwnd = _hwnd()
    if not hwnd:
        return False
    return not bool(ctypes.windll.user32.IsWindowVisible(wintypes.HWND(hwnd)))


def hide_window() -> bool:
    """收起进托盘：只是隐藏，进程和托盘图标都还在。"""
    hwnd = _hwnd()
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(wintypes.HWND(hwnd), 0)  # SW_HIDE
    return True


def show_window() -> bool:
    hwnd = _hwnd()
    if not hwnd:
        return False
    if _state["collapsed"]:
        ok = expand()
    else:
        # ShowWindow 返回的是「之前的可见状态」，不能拿来判断成功
        ctypes.windll.user32.ShowWindow(wintypes.HWND(hwnd), 5)  # SW_SHOW
        ok = bool(ctypes.windll.user32.IsWindowVisible(wintypes.HWND(hwnd)))
    ctypes.windll.user32.SetForegroundWindow(wintypes.HWND(hwnd))
    return ok


def toggle_visibility() -> bool:
    if is_hidden():
        return show_window()
    if _state["collapsed"]:
        return expand()
    return hide_window()


def minimize_window() -> bool:
    hwnd = _hwnd()
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(wintypes.HWND(hwnd), 6)  # SW_MINIMIZE
    return True


def close_window() -> bool:
    hwnd = _hwnd()
    if not hwnd:
        return False
    ctypes.windll.user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)  # WM_CLOSE
    return True


# ---------------------------------------------------------------------------
# 开机自启（HKCU\...\Run）
# ---------------------------------------------------------------------------
def autostart_command() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pythonw = Path(sys.executable)
    launcher = ROOT / "start_topotash.py"
    return f'"{pythonw}" "{launcher}" --floating --no-browser'


def autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except OSError:
                    pass
        return bool(enabled)
    except OSError as exc:
        print(f"[速记] 写入开机自启失败：{exc}", flush=True)
        return not enabled


# ---------------------------------------------------------------------------
# 全局热键
# ---------------------------------------------------------------------------
def register_hotkey(callback) -> bool:
    """独立线程 + RegisterHotKey + GetMessage 循环（WM_HOTKEY 投递给注册线程）。"""
    user32 = ctypes.windll.user32
    mod_alt, mod_control, mod_norepeat = 0x0001, 0x0002, 0x4000
    vk_n = 0x4E
    state = {"ok": False}

    def loop():
        if not user32.RegisterHotKey(None, 1, mod_control | mod_alt | mod_norepeat, vk_n):
            print(f"[速记] 热键 {HOTKEY_LABEL} 注册失败（可能被其他程序占用）", flush=True)
            return
        state["ok"] = True
        try:
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        callback()
                    except Exception as exc:  # pragma: no cover
                        print(f"[速记] 热键回调失败：{exc}", flush=True)
        finally:
            user32.UnregisterHotKey(None, 1)

    threading.Thread(target=loop, daemon=True, name="topotash-hotkey").start()
    time.sleep(0.15)
    return state["ok"]


# ---------------------------------------------------------------------------
# 服务进程
# ---------------------------------------------------------------------------
def spawn_server(port: int, db_path: str | None) -> subprocess.Popen | None:
    launcher = ROOT / "start_topotash.py"
    if not launcher.is_file():
        return None
    cmd = [sys.executable, str(launcher), "--port", str(port), "--no-browser"]
    if db_path:
        cmd.extend(["--db", db_path])
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.Popen(cmd, cwd=str(ROOT), creationflags=creation)
    except OSError as exc:
        print(f"[速记] 启动服务失败：{exc}", flush=True)
        return None


def workbench_url(port: int) -> str:
    return f"http://{HOST}:{port}/"


def open_workbench(port: int) -> bool:
    """用系统默认浏览器打开主站；返回是否成功发起。"""
    url = workbench_url(port)
    try:
        ok = bool(webbrowser.open(url))
        if not ok:
            os.startfile(url)  # 默认浏览器没注册时兜底
        return True
    except Exception as exc:
        print(f"[速记] 打开工作台失败：{exc}", flush=True)
        return False


def _safe_action(fn):
    """ctypes 回调里抛异常只会打一行 "Exception ignored"，这里兜住并记日志。"""
    def wrapper():
        try:
            fn()
        except Exception as exc:  # pragma: no cover - 托盘动作失败不该拖垮主进程
            print(f"[速记] 托盘动作失败：{type(exc).__name__}: {exc}", flush=True)
    return wrapper


def start_tray(port: int) -> bool:
    """等窗口出现后：去掉任务栏按钮 + 挂托盘图标。"""
    from tray_icon import TrayIcon, hide_from_taskbar

    def workbench() -> None:
        open_workbench(port)

    def toggle() -> None:
        toggle_visibility()

    def quit_app() -> None:
        hwnd = _hwnd()
        if hwnd:
            ctypes.windll.user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)

    def worker() -> None:
        hwnd = 0
        for _ in range(300):
            hwnd = _hwnd()
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            print("[速记] 没找到窗口，跳过托盘", flush=True)
            return
        hide_from_taskbar(hwnd)
        tray = TrayIcon(
            str(ROOT / "static" / "topotash.ico"),
            tooltip="TopoTash 速记",
            on_toggle=_safe_action(toggle),
            on_workbench=_safe_action(workbench),
            on_quit=_safe_action(quit_app),
        )
        ok = tray.start()
        _tray["obj"] = tray if ok else None
        if ok:
            print(f"[速记] 托盘图标已就绪（图标已注册：{tray.verify()}）", flush=True)
        else:
            print(f"[速记] 托盘图标创建失败：{tray.error}", flush=True)

    threading.Thread(target=worker, daemon=True, name="topotash-tray-init").start()
    return True


def fatal(message: str) -> None:
    print(f"[速记] {message}", flush=True)
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "TopoTash 速记", 0x10)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def run(flask_app=None, port: int = DEFAULT_PORT, db_path: str | None = None, debug: bool = False) -> int:
    redirect_streams()
    _handle, already = acquire_mutex()
    if already:
        if activate_existing():
            print("[速记] 已经有一个浮窗，已唤起", flush=True)
        else:
            print("[速记] 浮窗进程已存在（窗口可能刚被关闭）", flush=True)
        return 0

    if flask_app is not None:
        def serve():
            flask_app.run(host=HOST, port=port, debug=False, use_reloader=False, threaded=True)

        threading.Thread(target=serve, daemon=True, name="topotash-server").start()
    elif not port_open(port):
        spawn_server(port, db_path)

    if not wait_health(port, 30.0):
        fatal(f"服务没有启动起来（端口 {port}）。请先运行 start_topotash.py。")
        return 1

    try:
        import webview
    except ImportError:
        fatal("缺少 pywebview。请执行：\n  python -m pip install -r requirements-floating.txt")
        return 1

    width, height, x, y = load_geometry()
    x, y, width, height = clamp_to_screens(x, y, width, height)

    window = webview.create_window(
        WINDOW_TITLE,
        f"http://{HOST}:{port}/capture?shell=1",
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=(220, 40),
        frameless=True,
        easy_drag=False,   # 用自建的 WM_NCLBUTTONDOWN 拖动（pywebview 自带实现会抛异常）
        on_top=True,
        background_color="#FFFFFF",
        text_select=False,
    )

    bind_geometry(window)
    start_tray(port)
    register_hotkey(toggle_visibility)
    print(f"[速记] 浮窗已启动：http://{HOST}:{port}/capture（{HOTKEY_LABEL} 显示/隐藏）", flush=True)

    try:
        webview.start(debug=debug)
    finally:
        save_geometry(window)
    print("[速记] 浮窗已关闭", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TopoTash 速记浮窗")
    parser.add_argument("--port", type=int, default=int(os.environ.get("TOPOTASH_PORT", DEFAULT_PORT)))
    parser.add_argument("--db", help="数据库文件路径（仅在需要拉起服务时使用）")
    parser.add_argument("--debug", action="store_true", help="打开 WebView 调试")
    args = parser.parse_args(argv)
    return run(port=args.port, db_path=args.db, debug=args.debug)


if __name__ == "__main__":
    raise SystemExit(main())
