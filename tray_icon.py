"""Windows 托盘图标与任务栏隐藏（纯 ctypes，无第三方依赖）。

- `hide_from_taskbar(hwnd)`：给窗口加 WS_EX_TOOLWINDOW，去掉任务栏按钮
- `TrayIcon`：在独立线程里建消息窗口 + Shell_NotifyIcon，右键出菜单
"""
from __future__ import annotations

import ctypes
import os
import threading

from ctypes import wintypes

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x00000001, 0x00000002, 0x00000004
MF_STRING, MF_SEPARATOR = 0x00000000, 0x00000800
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x0100, 0x0002

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x0001, 0x0002, 0x0004, 0x0020
WS_POPUP = 0x80000000
TRAY_WINDOW_TITLE = "TopoTashTray"
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010

CMD_TOGGLE, CMD_WORKBENCH, CMD_QUIT = 1, 2, 3

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


def _configure() -> None:
    user32 = ctypes.windll.user32
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [
        wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, ctypes.c_void_p,
    ]
    user32.TrackPopupMenu.restype = ctypes.c_int
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    shell32 = ctypes.windll.shell32
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL


if os.name == "nt":
    _configure()


def _get_long(hwnd: int, index: int) -> int:
    user32 = ctypes.windll.user32
    fn = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    fn.argtypes = [wintypes.HWND, ctypes.c_int]
    fn.restype = ctypes.c_ssize_t
    return int(fn(wintypes.HWND(hwnd), index))


def _set_long(hwnd: int, index: int, value: int) -> None:
    user32 = ctypes.windll.user32
    fn = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    fn.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    fn.restype = ctypes.c_ssize_t
    fn(wintypes.HWND(hwnd), index, ctypes.c_ssize_t(value))


def hide_from_taskbar(hwnd: int) -> bool:
    """把窗口变成工具窗口：任务栏和 Alt+Tab 都不再出现。"""
    if os.name != "nt" or not hwnd:
        return False
    style = _get_long(hwnd, GWL_EXSTYLE)
    style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
    _set_long(hwnd, GWL_EXSTYLE, style)
    ctypes.windll.user32.SetWindowPos(
        wintypes.HWND(hwnd), None, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
    )
    return True


def has_toolwindow_style(hwnd: int) -> bool:
    return bool(_get_long(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW)


class TrayIcon:
    """右下角托盘图标 + 右键菜单。

    所有回调都在托盘线程里执行，调用方保证回调本身线程安全。
    """

    def __init__(self, icon_path: str, tooltip: str = "TopoTash 速记",
                 on_toggle=None, on_workbench=None, on_quit=None):
        self.icon_path = icon_path
        self.tooltip = tooltip
        self.on_toggle = on_toggle
        self.on_workbench = on_workbench
        self.on_quit = on_quit
        self.hwnd = 0
        self._thread = None
        self._ready = threading.Event()
        self._wndproc_ref = None
        self._hicon = None
        self.error = None

    # ------------------------------------------------------------------ 内部
    def _create_window(self) -> int:
        user32 = ctypes.windll.user32
        hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
        class_name = "TopoTashTrayWnd"
        self._wndproc_ref = WNDPROC(self._on_message)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassExW(ctypes.byref(wc))
        # 隐藏的 popup 窗口：不显示、不占任务栏，但 FindWindow 能找到（便于排查）
        return user32.CreateWindowExW(
            WS_POPUP, class_name, TRAY_WINDOW_TITLE, 0, 0, 0, 0, 0,
            None, None, hinst, None,
        )

    def _load_icon(self):
        if not os.path.isfile(self.icon_path):
            return None
        handle = ctypes.windll.user32.LoadImageW(
            None, self.icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
        )
        return handle or None

    def _nid(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip
        return nid

    def _add_icon(self) -> bool:
        nid = self._nid()
        return bool(ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))

    def verify(self) -> bool:
        """NIM_MODIFY 只在图标确实存在时成功，用来确认真的加进去了。"""
        if not self.hwnd:
            return False
        nid = self._nid()
        return bool(ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid)))

    def _remove_icon(self) -> None:
        if not self.hwnd:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def _show_menu(self) -> None:
        user32 = ctypes.windll.user32
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, CMD_TOGGLE, "展开 / 收起")
        user32.AppendMenuW(menu, MF_STRING, CMD_WORKBENCH, "打开工作台")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, "退出")
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(
            menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, point.x, point.y, 0, self.hwnd, None
        )
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)  # 让菜单正常关闭
        user32.DestroyMenu(menu)
        if cmd == CMD_TOGGLE and self.on_toggle:
            self.on_toggle()
        elif cmd == CMD_WORKBENCH and self.on_workbench:
            self.on_workbench()
        elif cmd == CMD_QUIT and self.on_quit:
            self.on_quit()

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                if self.on_toggle:
                    self.on_toggle()
                return 0
            if lparam == WM_RBUTTONUP:
                self._show_menu()
                return 0
        if msg == WM_COMMAND:
            code = wparam & 0xFFFF
            if code == CMD_QUIT and self.on_quit:
                self.on_quit()
            return 0
        if msg == WM_DESTROY:
            return 0
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _loop(self) -> None:
        try:
            self.hwnd = self._create_window()
            if not self.hwnd:
                self.error = "CreateWindowExW failed"
                return
            self._hicon = self._load_icon()
            if not self._add_icon():
                self.error = "Shell_NotifyIconW(NIM_ADD) failed"
                return
            self._ready.set()
            msg = wintypes.MSG()
            user32 = ctypes.windll.user32
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.restype = wintypes.BOOL
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:  # pragma: no cover - 托盘失败不该拖垮主程序
            self.error = str(exc)
        finally:
            try:
                self._remove_icon()
            except Exception:
                pass
            if not self._ready.is_set():
                self._ready.set()

    # ------------------------------------------------------------------ 对外
    def start(self, timeout: float = 3.0) -> bool:
        if os.name != "nt":
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="topotash-tray")
        self._thread.start()
        self._ready.wait(timeout)
        return self._ready.is_set() and not self.error

    def stop(self) -> None:
        self._remove_icon()
        if self.hwnd:
            ctypes.windll.user32.PostMessageW(wintypes.HWND(self.hwnd), WM_DESTROY, 0, 0)
