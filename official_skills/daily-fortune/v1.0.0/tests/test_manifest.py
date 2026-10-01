"""app.yaml / SKILL.md / 构建产物三者的一致性。

这些断言随包一起安装，用来在运行环境里直接暴露「改了 app.yaml 或模板忘了重新构建 UI」
这类问题；开发期更全面的结构校验用 app-skill-creator 的 validate_app_skill.py。
"""

import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

APP_ROOT = Path(__file__).resolve().parents[1]
APP_ID = "daily-fortune"
RESOURCE_URI = "ui://daily-fortune/main"
TOOL_NAME = "daily_fortune"
MIME_TYPE = "text/html;profile=mcp-app"


@unittest.skipIf(yaml is None, "PyYAML not installed")
class ManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = yaml.safe_load(
            (APP_ROOT / "assets" / "app.yaml").read_text(encoding="utf-8")
        )

    def test_id_matches_directory_and_resource_uri(self):
        self.assertEqual(self.manifest["id"], APP_ID)
        self.assertEqual(APP_ROOT.name, APP_ID)
        self.assertTrue(RESOURCE_URI.startswith(f"ui://{APP_ID}/"))

    def test_resource_declares_mcp_app_mime_and_existing_path(self):
        resources = self.manifest["resources"]
        self.assertTrue(resources)
        for resource in resources:
            self.assertEqual(resource["mimeType"], MIME_TYPE)
            self.assertTrue((APP_ROOT / resource["path"]).is_file(), resource["path"])

    def test_tool_binds_declared_resource_and_existing_handler(self):
        declared = {resource["uri"] for resource in self.manifest["resources"]}
        tools = self.manifest["tools"]
        self.assertTrue(tools)
        for tool in tools:
            handler = tool["handler"]["path"]
            self.assertTrue((APP_ROOT / handler).is_file(), handler)
            # resourceUri / visibility 必须放在 _meta.ui 下：后端 manifest 解析只读这个位置。
            ui_meta = tool["_meta"]["ui"]
            self.assertIn(ui_meta["resourceUri"], declared)
            self.assertTrue(set(ui_meta["visibility"]) <= {"model", "app"})

    def test_input_schema_pins_operation_and_rejects_stray_fields(self):
        tool = next(item for item in self.manifest["tools"] if item["name"] == TOOL_NAME)
        schema = tool["inputSchema"]
        self.assertIn("operation", schema["required"])
        self.assertTrue(schema["properties"]["operation"]["enum"])
        # 字段白名单能让模型的错别字在 CLI 层就失败，而不是被静默丢弃。
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("timekey", schema["properties"])
        # 订阅能力已移除：push_time / frequency 不能再出现在契约里。
        self.assertNotIn("push_time", schema["properties"])
        self.assertNotIn("frequency", schema["properties"])
        self.assertNotIn("push_time", schema["properties"].get("operation", {}).get("enum", []))
        for removed in ["subscribe", "set_push_time", "unsubscribe", "list_subscriptions"]:
            self.assertNotIn(removed, schema["properties"]["operation"]["enum"])


class BuiltUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (APP_ROOT / "assets" / "ui" / "index.html").read_text(encoding="utf-8")

    def test_bridge_is_inlined(self):
        self.assertNotIn("/*__MCP_BRIDGE__*/", self.html, "构建产物过期，请先 npm run build:ui")
        self.assertIn("ui/initialize", self.html)

    def test_built_artifact_is_not_stale(self):
        built = APP_ROOT / "assets" / "ui" / "index.html"
        source = APP_ROOT / "assets" / "ui" / "index.template"
        # 容差 1 秒：部分文件系统的 st_mtime 精度不足，同一次构建里两个文件可能差几毫秒，
        # 严格比较会偶发误报。真正的过期（差几秒以上）照样拦得住。
        self.assertGreaterEqual(built.stat().st_mtime + 1, source.stat().st_mtime)

    def test_no_external_subresources(self):
        # iframe 里 CSP 会拦掉外部子资源，构建产物必须完全自包含。
        pattern = re.compile(
            r"""<(?:script|link|img|iframe|source|video|audio|embed|object)\b[^>]*?"""
            r"""\b(?:src|href|data)\s*=\s*["']https?://""",
            re.I | re.S,
        )
        found = pattern.search(self.html)
        self.assertIsNone(found, f"构建产物从外部加载子资源：{found.group(0) if found else ''}")


class SkillContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (APP_ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_teaches_only_the_unified_cli(self):
        self.assertIn(f"app {APP_ID} {TOOL_NAME}", self.skill)
        self.assertIn(f"app {APP_ID} describe", self.skill)
        self.assertIn(f"app {APP_ID} toollist", self.skill)
        # 直跑 handler 不会产出 marker，UI 不会刷新，SKILL.md 必须明确禁止。
        self.assertIn(f"禁止直接执行 `{TOOL_NAME}.py`", self.skill)

    def test_keeps_core_sections(self):
        for heading in (
            "## 角色与入口",
            "## 执行优先级（严格约束，单一真源）",
            "## Agent 操作",
            "## 字段说明",
            "## 常见坑",
            "## 沟通规则",
        ):
            self.assertIn(heading, self.skill)


if __name__ == "__main__":
    unittest.main()
