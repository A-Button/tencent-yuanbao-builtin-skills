#!/usr/bin/env python3

from __future__ import annotations

import base64
import io
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from audit_xcard_visuals import audit_component  # noqa: E402


def data_uri(image: Image.Image) -> str:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


class VisualAuditTest(unittest.TestCase):
    def test_near_circular_text_button_warns(self) -> None:
        findings = audit_component(
            {
                "id": "select",
                "component": "Button",
                "style": {"width": 46, "height": 40},
            },
            "button",
            expect_scroll=False,
        )
        self.assertTrue(any("near-circular" in finding.message for finding in findings))

    def test_wide_text_button_passes(self) -> None:
        findings = audit_component(
            {
                "id": "select",
                "component": "Button",
                "style": {"width": 64, "height": 40},
            },
            "button",
            expect_scroll=False,
        )
        self.assertFalse(findings)

    def test_circular_image_with_white_matte_warns(self) -> None:
        image = Image.new("RGBA", (80, 80), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((16, 16, 64, 64), fill=(20, 40, 120, 255))
        findings = audit_component(
            {
                "id": "logo",
                "component": "Image",
                "url": data_uri(image),
                "style": {"width": 40, "height": 40, "shape": 20},
            },
            "image",
            expect_scroll=False,
        )
        self.assertTrue(
            any("near-white perimeter" in finding.message for finding in findings)
        )

    def test_scroll_expectation_requires_height(self) -> None:
        findings = audit_component(
            {
                "id": "stores",
                "component": "List",
                "direction": "vertical",
                "children": {"path": "shops", "componentId": "store"},
            },
            "list",
            expect_scroll=True,
        )
        self.assertTrue(
            any("no numeric style.height" in finding.message for finding in findings)
        )


if __name__ == "__main__":
    unittest.main()
