"""
tests/test_tray.py — Unit tests for system tray module.
"""

import unittest
from PIL import Image

from jarvis.tray import _make_icon


class TestTray(unittest.TestCase):
    def test_make_icon(self):
        """_make_icon should create a valid RGBA PIL image."""
        img = _make_icon(size=64)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
