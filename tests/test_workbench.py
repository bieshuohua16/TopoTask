"""托盘「打开工作台」：URL 拼装与浏览器调用（不真的开浏览器）。"""
from __future__ import annotations

import unittest
from unittest import mock

import quick_capture as qc


class WorkbenchTest(unittest.TestCase):
    def test_url(self):
        self.assertEqual(qc.workbench_url(5000), "http://127.0.0.1:5000/")

    def test_opens_default_browser(self):
        with mock.patch.object(qc.webbrowser, "open", return_value=True) as opened:
            self.assertTrue(qc.open_workbench(5123))
        opened.assert_called_once_with("http://127.0.0.1:5123/")

    def test_falls_back_to_startfile(self):
        with mock.patch.object(qc.webbrowser, "open", return_value=False), \
                mock.patch.object(qc.os, "startfile", create=True) as started:
            self.assertTrue(qc.open_workbench(5000))
        started.assert_called_once_with("http://127.0.0.1:5000/")

    def test_survives_browser_error(self):
        with mock.patch.object(qc.webbrowser, "open", side_effect=OSError("boom")):
            self.assertFalse(qc.open_workbench(5000))


if __name__ == "__main__":
    unittest.main()
