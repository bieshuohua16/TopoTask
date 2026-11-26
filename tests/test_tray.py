"""任务栏隐藏：真实窗口上的样式验证（屏幕外 Tk 窗口）。"""
from __future__ import annotations

import os
import unittest

import tray_icon

try:  # pragma: no cover
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None


@unittest.skipUnless(os.name == "nt" and tk is not None, "仅 Windows + tkinter")
class TaskbarStyleTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter 不可用：{exc}")
        self.root.title("TopoTash Tray Test")
        self.root.geometry("300x120+-2400+-2400")
        self.root.update()
        # winfo_id 是 Tk 子窗口，wm_frame 才是带任务栏按钮的顶层窗口
        frame = self.root.wm_frame()
        self.hwnd = int(frame, 16) if isinstance(frame, str) else int(frame)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:  # pragma: no cover
            pass

    def test_hide_from_taskbar_sets_toolwindow(self):
        self.assertFalse(tray_icon.has_toolwindow_style(self.hwnd))
        self.assertTrue(tray_icon.hide_from_taskbar(self.hwnd))
        self.assertTrue(tray_icon.has_toolwindow_style(self.hwnd))

    def test_hide_from_taskbar_is_idempotent(self):
        tray_icon.hide_from_taskbar(self.hwnd)
        self.assertTrue(tray_icon.hide_from_taskbar(self.hwnd))
        self.assertTrue(tray_icon.has_toolwindow_style(self.hwnd))

    def test_no_window_is_safe(self):
        self.assertFalse(tray_icon.hide_from_taskbar(0))


if __name__ == "__main__":
    unittest.main()
