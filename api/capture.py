"""桌面浮窗的窗口动作（最小化 / 关闭 / 开机自启）。

这些操作走本地 HTTP，而不是 pywebview 的 js_api：
WebView2 的 JS→Python 桥在 WinForms 上跨线程访问 COM 会卡死整个进程，
用 ctypes 直接操作窗口句柄 + 注册表，任一线程调用都安全。
"""
from __future__ import annotations

import ctypes
import os

from flask import Blueprint, jsonify, request

from quick_capture import (
    autostart_enabled,
    close_window,
    show_window,
    collapse,
    expand,
    hide_window,
    is_collapsed,
    is_hidden,
    tray_ready,
    minimize_window,
    move_to,
    set_autostart,
    window_rect,
)

bp = Blueprint("capture", __name__, url_prefix="/api/capture")

SW_MINIMIZE = 6
WM_CLOSE = 0x0010


def _hwnd():
    if os.name != "nt":
        return 0
    try:
        return ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
    except Exception:
        return 0


@bp.post("/window")
def window_action():
    action = (request.get_json(silent=True) or {}).get("action")
    try:
        if action == "collapse":
            ok = collapse()
        elif action == "expand":
            ok = expand()
        elif action == "move":
            payload = request.get_json(silent=True) or {}
            ok = move_to(int(payload.get("x", 0)), int(payload.get("y", 0)))
        elif action == "minimize":
            ok = minimize_window()
        elif action == "close":
            ok = hide_window()          # × = 收进托盘，不退出
        elif action == "hide":
            ok = hide_window()
        elif action == "show":
            ok = show_window()
        else:
            return jsonify({"ok": False, "error": "unknown_action"}), 400
    except Exception as exc:  # pragma: no cover - 仅 Windows
        return jsonify({"ok": False, "error": str(exc)}), 500
    if not ok:
        return jsonify({"ok": False, "error": "window_not_found"}), 404
    return jsonify({"ok": True, "action": action})


@bp.get("/state")
def get_state():
    x, y, width, height = window_rect()
    return jsonify(
        {
            "shell": True,
            "collapsed": is_collapsed(),
            "hidden": is_hidden(),
            "tray": tray_ready(),
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
    )


@bp.get("/autostart")
def get_autostart():
    return jsonify({"enabled": autostart_enabled()})


@bp.put("/autostart")
def put_autostart():
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    return jsonify({"enabled": set_autostart(enabled)})
