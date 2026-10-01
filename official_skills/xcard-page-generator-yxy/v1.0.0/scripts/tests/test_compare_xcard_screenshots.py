#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

import sys

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from compare_xcard_screenshots import crop_image, parse_crop, resize_width  # noqa: E402


class ScreenshotComparisonTest(unittest.TestCase):
    def test_parse_crop(self) -> None:
        self.assertEqual(parse_crop("1,2,30,40"), (1, 2, 30, 40))

    def test_crop_and_resize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            Image.new("RGB", (100, 80), "white").save(path)
            cropped, report = crop_image(path, (10, 5, 60, 40))
            resized = resize_width(cropped, 300)
        self.assertEqual(cropped.size, (60, 40))
        self.assertEqual(resized.size, (300, 200))
        self.assertEqual(report["crop"], [10, 5, 60, 40])


if __name__ == "__main__":
    unittest.main()
