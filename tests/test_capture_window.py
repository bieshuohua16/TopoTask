"""真实窗口上的收起 / 展开（用屏幕外的 Tk 窗口，不打扰桌面）。"""
from __future__ import annotations

import os
import unittest

import quick_capture as qc

try:  # pragma: no cover - 环境缺 tkinter 时跳过
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None


@unittest.skipUnless(os.name == "nt" and tk is not None, "仅 Windows + tkinter")
class CollapseRealWindowTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter 不可用：{exc}")
        self.root.title(qc.WINDOW_TITLE)
        self.root.geometry("420x620+-2400+-2400")   # 放到虚拟屏外面
        self.root.update()
        qc._state.update(collapsed=False, expanded=None)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:  # pragma: no cover
            pass
        qc._state.update(collapsed=False, expanded=None)

    def test_finds_own_window(self):
        self.assertNotEqual(qc._hwnd(), 0)

    def test_collapse_to_pill_and_back(self):
        before = qc._rect(qc._hwnd())
        self.assertTrue(qc.collapse())
        _, _, width, height = qc._rect(qc._hwnd())
        self.assertEqual((width, height), qc.pill_size(qc._hwnd()))
        self.assertTrue(qc.is_collapsed())

        self.assertTrue(qc.expand())
        self.assertEqual(qc._rect(qc._hwnd()), before)
        self.assertFalse(qc.is_collapsed())

    def test_collapse_keeps_right_edge(self):
        before = qc._rect(qc._hwnd())
        qc.collapse()
        after = qc._rect(qc._hwnd())
        self.assertEqual(before[0] + before[2], after[0] + after[2])
        self.assertEqual(before[1], after[1])


if __name__ == "__main__":
    unittest.main()
