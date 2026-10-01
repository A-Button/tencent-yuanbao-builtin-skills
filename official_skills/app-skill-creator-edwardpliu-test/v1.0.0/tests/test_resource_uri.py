"""资源命名、脚手架工具绑定与混合视图的回归测试。"""

import argparse
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from init_app_skill import scaffold
from validate_app_skill import A2UI_MIME_TYPE, MIME_TYPE, Report, check_resources, check_tools


class ResourceUriTest(unittest.TestCase):
    def test_a2ui_uri_validation(self):
        cases = {
            "ai_apps.skills.book_recommender_res": True,
            "ai_apps.skills.book_recommender_card_res": True,
            "ai_apps.skills.book_recommender_search_results_res": True,
            "ui://book-recommender/main": False,
            "ai_apps.skills.book-recommender_card_res": False,
            "ai_apps.skills.other_card_res": False,
            "ai_apps.skills.book_recommender_card": False,
            "ai_apps.skills.book_recommender__res": False,
            "ai_apps.skills.book_recommender_search-results_res": False,
            "ai_apps.skills.book_recommender_card_res/extra": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "card.json").write_text("{}")
            for app_id in ("book-recommender", "book_recommender"):
                for uri, valid in cases.items():
                    with self.subTest(app_id=app_id, uri=uri):
                        report = Report(root)
                        check_resources(report, root, {"resources": [{
                            "uri": uri, "mimeType": A2UI_MIME_TYPE, "path": "card.json",
                        }]}, app_id)
                        self.assertEqual(not report.errors, valid, report.errors)

    def test_generated_resources_and_tool_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("a2ui", "h5"):
                for app_id in ("book-recommender", "book_recommender"):
                    with self.subTest(mode=mode, app_id=app_id):
                        root = scaffold(argparse.Namespace(
                            app_id=app_id, path=str(Path(directory) / mode),
                            entity="book", entity_plural="books", name="图书推荐",
                            description="图书推荐", version="v1.0", ui_mode=mode,
                            store="json", force=False,
                        ))
                        manifest = yaml.safe_load((root / "assets/app.yaml").read_text())
                        expected = (
                            "ai_apps.skills.book_recommender_card_res"
                            if mode == "a2ui" else f"ui://{app_id}/main"
                        )
                        self.assertEqual(manifest["resources"][0]["uri"], expected)
                        for tool in manifest["tools"]:
                            self.assertEqual(tool["_meta"]["ui"]["resourceUri"], expected)
                        # 此测试不涉及前端构建，只补齐资源文件以校验 URI 和工具引用。
                        for resource in manifest["resources"]:
                            if resource["mimeType"] == MIME_TYPE:
                                (root / resource["path"]).write_text("<!doctype html>")
                        report = Report(root)
                        resources = check_resources(report, root, manifest, app_id)
                        check_tools(report, root, manifest, resources)
                        self.assertEqual(report.errors, [])
                        if mode == "a2ui":
                            spec = importlib.util.spec_from_file_location(
                                "generated_manifest", root / "tests/test_manifest.py",
                            )
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.ManifestTest)
                            result = unittest.TestResult()
                            suite.run(result)
                            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)

    def test_h5_rejects_a2ui_uri(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workspace.html").write_text("<!doctype html>")
            report = Report(root)
            check_resources(report, root, {"resources": [{
                "uri": "ai_apps.skills.book_recommender_res",
                "mimeType": MIME_TYPE, "path": "workspace.html",
            }]}, "book-recommender")
            self.assertEqual(len(report.errors), 1)
            self.assertIn("H5 uri", report.errors[0])


if __name__ == "__main__":
    unittest.main()
