"""app.yaml / SKILL.md / 构建产物三者的一致性。"""

import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

APP_ROOT = Path(__file__).resolve().parents[1]
APP_ID = "book-recommender"
RESOURCE_URI = "ui://book-recommender/main"
WORKSPACE_URI = "ui://book-recommender/workspace"
TOOL_NAMES = {"list_books", "search_books", "recommend_books"}
A2UI_MIME = "application/a2ui+json"
HTML_MIME = "text/html;profile=mcp-app"


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

    def test_resource_declares_known_mime_and_existing_path(self):
        resources = self.manifest["resources"]
        self.assertTrue(resources)
        for resource in resources:
            self.assertIn(resource["mimeType"], {A2UI_MIME, HTML_MIME})
            self.assertTrue((APP_ROOT / resource["path"]).is_file(), resource["path"])
        by_uri = {resource["uri"]: resource for resource in resources}
        self.assertEqual(by_uri[RESOURCE_URI]["mimeType"], A2UI_MIME)
        self.assertEqual(by_uri[WORKSPACE_URI]["mimeType"], HTML_MIME)

    def test_card_reaches_workspace_through_open_workspace(self):
        import json
        card = json.loads(
            (APP_ROOT / "assets" / "ui" / "card.json").read_text(encoding="utf-8")
        )
        targets = {
            (component.get("action") or {}).get("event", {}).get("context", {}).get("resourceUri")
            for component in card["components"]
            if isinstance(component, dict)
            and (component.get("action") or {}).get("event", {}).get("name") == "open_workspace"
        }
        self.assertIn(WORKSPACE_URI, targets, "卡片没有 open_workspace 指向工作区")
        declared = {resource["uri"] for resource in self.manifest["resources"]}
        self.assertTrue(targets <= declared, f"转场目标未在 resources 声明：{targets - declared}")

    def test_tools_are_three_separate_operations(self):
        """一个操作一个 tool，不合并再用 operation 分派。"""
        tool_names = {tool["name"] for tool in self.manifest["tools"]}
        self.assertEqual(tool_names, TOOL_NAMES)
        for tool in self.manifest["tools"]:
            handler = tool["handler"]["path"]
            self.assertTrue((APP_ROOT / handler).is_file(), handler)
            ui_meta = tool["_meta"]["ui"]
            self.assertIn(ui_meta["resourceUri"],
                         {r["uri"] for r in self.manifest["resources"]})
            self.assertTrue(set(ui_meta["visibility"]) <= {"model", "app"})
            # 每个 tool 有自己的 inputSchema，不再共用一份。
            schema = tool["inputSchema"]
            self.assertIsInstance(schema, dict)
            # list_books 不接受参数
            if tool["name"] == "list_books":
                self.assertFalse(schema.get("required"))
                self.assertFalse(schema.get("properties"))
            elif tool["name"] == "search_books":
                self.assertIn("query", schema["required"])
            elif tool["name"] == "recommend_books":
                self.assertIn("category", schema["properties"])
                self.assertIn("count", schema["properties"])


class BuiltUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (APP_ROOT / "assets" / "ui" / "workspace.html").read_text(encoding="utf-8")

    def test_bridge_is_inlined(self):
        self.assertNotIn("/*__MCP_BRIDGE__*/", self.html, "构建产物过期，请先 npm run build:ui")
        self.assertIn("ui/initialize", self.html)

    def test_no_external_subresources(self):
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
        self.assertIn(f"app {APP_ID} <tool_name>", self.skill)
        self.assertIn(f"app {APP_ID} describe", self.skill)
        self.assertIn(f"app {APP_ID} toollist", self.skill)
        # 禁止直跑 handler
        self.assertIn("禁止直接执行", self.skill)

    def test_keeps_core_sections(self):
        for heading in (
            "## 角色与入口",
            "## 执行优先级（严格约束，单一真源）",
            "## 工具一览",
            "## Agent 使用指南",
            "## 字段说明",
            "## 常见坑",
            "## 沟通规则",
        ):
            self.assertIn(heading, self.skill)

    def test_three_tools_documented(self):
        for name in TOOL_NAMES:
            self.assertIn(name, self.skill, f"SKILL.md 缺少工具 {name} 的说明")


if __name__ == "__main__":
    unittest.main()