#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_xcard_bundle import BundleValidator  # noqa: E402


class BundleValidatorTest(unittest.TestCase):
    def new_validator(self) -> BundleValidator:
        resource_root = Path(__file__).resolve().parents[4]
        return BundleValidator(resource_root, None, set())

    def write_jsonl(self, directory: Path, messages: list[dict]) -> Path:
        path = directory / "sample.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(message, ensure_ascii=False, separators=(",", ":"))
                for message in messages
            ),
            encoding="utf-8",
        )
        return path

    def test_valid_inline_surface(self) -> None:
        messages = [
            {
                "version": "v1.0",
                "createSurface": {
                    "surfaceId": "test-surface",
                    "catalogId": "https://yuanbao.tencent.com/specification/v1_0/catalogs/xcard/catalog.json",
                },
            },
            {
                "version": "v1.0",
                "updateComponents": {
                    "surfaceId": "test-surface",
                    "components": [
                        {
                            "id": "root",
                            "component": "Text",
                            "text": {"path": "/title"},
                            "variant": "h4",
                        }
                    ],
                },
            },
            {
                "version": "v1.0",
                "updateDataModel": {
                    "surfaceId": "test-surface",
                    "path": "/",
                    "value": {"title": "Title"},
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_jsonl(Path(directory), messages)
            validator = self.new_validator()
            validator.validate_jsonl(path)
        self.assertFalse(
            [issue for issue in validator.issues if issue.severity == "error"]
        )

    def test_missing_root_is_rejected(self) -> None:
        messages = [
            {
                "version": "v1.0",
                "createSurface": {"surfaceId": "test-surface"},
            },
            {
                "version": "v1.0",
                "updateComponents": {
                    "surfaceId": "test-surface",
                    "components": [
                        {"id": "title", "component": "Text", "text": "Title"}
                    ],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_jsonl(Path(directory), messages)
            validator = self.new_validator()
            validator.validate_jsonl(path)
        self.assertTrue(
            any("id='root'" in issue.message for issue in validator.issues)
        )

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.jsonl"
            path.write_text(
                '{"version":"v1.0","version":"v1.0","createSurface":{"surfaceId":"s"}}',
                encoding="utf-8",
            )
            validator = self.new_validator()
            validator.validate_jsonl(path)
        self.assertTrue(
            any("duplicate JSON key" in issue.message for issue in validator.issues)
        )

    def test_template_binding_must_be_relative(self) -> None:
        validator = self.new_validator()
        validator.validate_template(
            Path("template.json"),
            {
                "version": "v1.0",
                "updateComponents": {
                    "surfaceId": "template",
                    "components": [
                        {
                            "id": "root",
                            "component": "Text",
                            "text": {"path": "/title"},
                        }
                    ],
                },
            },
        )
        self.assertTrue(
            any(
                "template bindings must be relative" in issue.message
                for issue in validator.issues
            )
        )

    def test_stepper_supports_relative_dynamic_bounds_in_template(self) -> None:
        validator = self.new_validator()
        validator.validate_template(
            Path("template.json"),
            {
                "version": "v1.0",
                "updateComponents": {
                    "surfaceId": "template",
                    "components": [
                        {
                            "id": "root",
                            "component": "Stepper",
                            "label": {"path": "quantity/label"},
                            "value": {"path": "quantity/value"},
                            "min": {"path": "quantity/min"},
                            "max": {"path": "quantity/max"},
                            "step": {"path": "quantity/step"},
                        }
                    ],
                },
            },
        )
        self.assertFalse(
            [issue for issue in validator.issues if issue.severity == "error"]
        )

    def test_typography_overlay_key_must_be_lowercase(self) -> None:
        validator = self.new_validator()
        validator.validate_token_overlay(
            Path("overlay.tokens.json"),
            {
                "typography": {
                    "originalPrice": {
                        "size": 12,
                        "weight": 400,
                        "lineHeight": 18,
                        "color": "basic_text_disabled",
                    }
                }
            },
        )
        self.assertTrue(
            any(
                "typography keys must be lowercase" in issue.message
                for issue in validator.issues
            )
        )

    def test_message_envelope_is_schema_checked(self) -> None:
        messages = [
            {
                "version": "v1.0",
                "createSurface": {
                    "surfaceId": "test-surface",
                    "catalogId": 123,
                    "sendDataModel": "yes",
                    "typo": True,
                    "components": [
                        {"id": "root", "component": "Text", "text": "Title"}
                    ],
                },
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_jsonl(Path(directory), messages)
            validator = self.new_validator()
            validator.validate_jsonl(path)
        messages = [issue.message for issue in validator.issues]
        self.assertTrue(any("catalogId" in message for message in messages))
        self.assertTrue(any("sendDataModel" in message for message in messages))
        self.assertTrue(any("unsupported property 'typo'" in message for message in messages))

    def test_function_arguments_are_schema_checked(self) -> None:
        messages = [
            {
                "version": "v1.0",
                "createSurface": {"surfaceId": "test-surface"},
            },
            {
                "version": "v1.0",
                "updateComponents": {
                    "surfaceId": "test-surface",
                    "components": [
                        {
                            "id": "root",
                            "component": "Text",
                            "text": {
                                "call": "formatCurrency",
                                "args": {"value": 10},
                            },
                        }
                    ],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_jsonl(Path(directory), messages)
            validator = self.new_validator()
            validator.validate_jsonl(path)
        self.assertTrue(
            any(
                "missing required property 'currency'" in issue.message
                for issue in validator.issues
            )
        )

    def test_check_and_event_shapes_are_schema_checked(self) -> None:
        messages = [
            {
                "version": "v1.0",
                "createSurface": {"surfaceId": "test-surface"},
            },
            {
                "version": "v1.0",
                "updateComponents": {
                    "surfaceId": "test-surface",
                    "components": [
                        {
                            "id": "root",
                            "component": "Button",
                            "child": "label",
                            "checks": [
                                {
                                    "condition": {
                                        "call": "required",
                                        "args": {},
                                    }
                                }
                            ],
                            "action": {
                                "event": {
                                    "name": "submit",
                                    "unexpected": True,
                                }
                            },
                        },
                        {
                            "id": "label",
                            "component": "Text",
                            "text": "Submit",
                        },
                    ],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_jsonl(Path(directory), messages)
            validator = self.new_validator()
            validator.validate_jsonl(path)
        messages = [issue.message for issue in validator.issues]
        self.assertTrue(
            any("missing required property 'value'" in message for message in messages)
        )
        self.assertTrue(
            any("unsupported event properties" in message for message in messages)
        )

    def test_overlay_cannot_add_new_token_roles(self) -> None:
        validator = self.new_validator()
        validator.validate_token_overlay(
            Path("overlay.tokens.json"),
            {
                "colors": {
                    "new_brand": {
                        "light": "#112233FF",
                        "dark": "#112233FF",
                    }
                },
                "typography": {
                    "newtitle": {
                        "size": 16,
                        "weight": 600,
                        "lineHeight": 22,
                        "color": "new_brand",
                    }
                },
            },
        )
        self.assertTrue(
            any(
                "overlay can only override an existing" in issue.message
                for issue in validator.issues
            )
        )


if __name__ == "__main__":
    unittest.main()
