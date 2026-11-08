"""Tests for the Windows first-run wizard helpers and the icon generator."""
from __future__ import annotations

import struct
import unittest

from setup_first_run import human_size, _flask_compatible
from tools.make_icon import encode_ico, render_rgba


class IconGeneratorTest(unittest.TestCase):
    def test_ico_header_and_entries(self):
        data = encode_ico((16, 32))

        reserved, image_type, count = struct.unpack("<HHH", data[:6])
        self.assertEqual((reserved, image_type, count), (0, 1, 2))

        entries = [
            struct.unpack("<BBBBHHII", data[6 + 16 * index:22 + 16 * index])
            for index in range(count)
        ]
        self.assertEqual([entry[0] for entry in entries], [16, 32])
        for entry, size in zip(entries, (16, 32)):
            width, height, colors, _, planes, bit_count, length, offset = entry
            self.assertEqual((width, height), (size, size))
            self.assertEqual((colors, planes, bit_count), (0, 1, 32))
            self.assertGreater(length, 0)
            self.assertLessEqual(offset + length, len(data))

    def test_render_uses_brand_blue(self):
        rgba = render_rgba(32)
        offset = (5 * 32 + 5) * 4
        red, green, blue, alpha = rgba[offset:offset + 4]
        self.assertEqual(alpha, 255)
        self.assertGreater(blue, red, "图标底色应为靛蓝渐变")
        self.assertGreater(blue, green)

    def test_render_is_transparent_at_rounded_corner(self):
        rgba = render_rgba(32)
        self.assertEqual(len(rgba), 32 * 32 * 4)
        self.assertEqual(rgba[3], 0, "左上角应在圆角之外")
        center = (16 * 32 + 16) * 4
        self.assertEqual(rgba[center + 3], 255, "中心应完全不透明")


class WizardHelpersTest(unittest.TestCase):
    def test_flask_version_range(self):
        self.assertTrue(_flask_compatible("3.1.3"))
        self.assertFalse(_flask_compatible("2.3.0"))
        self.assertFalse(_flask_compatible("4.0.0"))
        self.assertFalse(_flask_compatible("not-a-version"))

    def test_human_size(self):
        self.assertEqual(human_size(512), "512 B")
        self.assertEqual(human_size(1024), "1.0 KB")
        self.assertEqual(human_size(3 * 1024 * 1024), "3.0 MB")


if __name__ == "__main__":
    unittest.main()
