"""收起 / 展开成标题栏的几何计算（不依赖真实窗口）。"""
from __future__ import annotations

import unittest

import quick_capture as qc


class CollapseGeometryTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._orig = (qc._hwnd, qc._rect, qc._place)
        qc._hwnd = lambda: 123
        qc._rect = lambda hwnd: (1000, 100, 420, 620)
        qc._place = lambda hwnd, x, y, w, h, flags=0: (self.calls.append((int(x), int(y), int(w), int(h))) or True)
        qc._dpi_scale = lambda hwnd: 1.0
        qc._state.update(collapsed=False, expanded=None)

    def tearDown(self):
        qc._hwnd, qc._rect, qc._place = self._orig
        qc._state.update(collapsed=False, expanded=None)

    def test_collapse_keeps_right_edge(self):
        self.assertTrue(qc.collapse())
        # 右边缘 1420 不动：1420 - 260 = 1160
        self.assertEqual(self.calls[-1], (1160, 100, 260, 44))
        self.assertTrue(qc.is_collapsed())

    def test_expand_restores_saved_rect(self):
        qc.collapse()
        self.calls.clear()
        self.assertTrue(qc.expand())
        self.assertEqual(self.calls[-1], (1000, 100, 420, 620))
        self.assertFalse(qc.is_collapsed())

    def test_move_to_keeps_size(self):
        self.assertTrue(qc.move_to(500, 200))
        # 尺寸沿用当前窗口，只改坐标
        self.assertEqual(self.calls[-1], (500, 200, 420, 620))

    def test_toggle_alternates(self):
        qc.toggle_collapsed()
        self.assertTrue(qc.is_collapsed())
        qc.toggle_collapsed()
        self.assertFalse(qc.is_collapsed())

    def test_collapse_twice_keeps_original_rect(self):
        qc.collapse()
        qc.collapse()  # 第二次不应把 260×44 当成「展开尺寸」
        self.calls.clear()
        qc.expand()
        self.assertEqual(self.calls[-1], (1000, 100, 420, 620))

    def test_no_window_is_safe(self):
        qc._hwnd = lambda: 0
        self.assertFalse(qc.collapse())
        self.assertFalse(qc.expand())
        self.assertFalse(qc.move_to(10, 10))
        self.assertFalse(qc.minimize_window())
        self.assertFalse(qc.close_window())


if __name__ == "__main__":
    unittest.main()
