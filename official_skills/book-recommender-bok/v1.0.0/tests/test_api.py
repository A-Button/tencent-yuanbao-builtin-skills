import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Optional

APP_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = APP_ROOT / "scripts"


class ApiTest(unittest.TestCase):
    @staticmethod
    def run_handler(script: str, payload: Optional[dict] = None) -> dict:
        """经真实子进程调用单个 handler，顺带验证 stdout 恰好是一行 JSON。"""
        payload = payload or {}
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / script), json.dumps(payload)],
            capture_output=True,
            text=True,
            cwd=str(SCRIPTS),
            check=False,
        )
        self = unittest.TestCase()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"stdout 必须只有一行 JSON：{completed.stdout!r}")
        return json.loads(lines[0])


class ListBooksTest(unittest.TestCase):
    def _invoke(self, payload=None):
        return ApiTest.run_handler("list_books.py", payload)

    def test_returns_all_books_and_categories(self):
        result = self._invoke()
        self.assertGreater(result["count"], 0)
        self.assertEqual(len(result["books"]), result["count"])
        self.assertIsInstance(result["categories"], list)
        self.assertIn("文学", result["categories"])

    def test_rejects_extra_args(self):
        result = self._invoke({"extra": "x"})
        self.assertEqual(result["code"], "INVALID_ARGUMENT")

    def test_every_book_has_required_fields(self):
        result = self._invoke()
        for b in result["books"]:
            self.assertIn("id", b)
            self.assertIn("title", b)
            self.assertIn("author", b)
            self.assertIn("rating", b)
            self.assertIn("category", b)
            self.assertIn("description", b)
            self.assertIsInstance(b["rating"], (int, float))


class SearchBooksTest(unittest.TestCase):
    def _invoke(self, payload=None):
        return ApiTest.run_handler("search_books.py", payload)

    def test_search_by_title(self):
        result = self._invoke({"query": "三体"})
        self.assertGreater(result["count"], 0)
        self.assertIn("三体", [b["title"] for b in result["books"]])

    def test_search_by_author(self):
        result = self._invoke({"query": "余华"})
        self.assertGreater(result["count"], 0)
        self.assertIn("活着", [b["title"] for b in result["books"]])

    def test_search_no_match(self):
        result = self._invoke({"query": "不存在的书xyz"})
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["books"], [])

    def test_missing_query_fails(self):
        result = self._invoke({})
        self.assertEqual(result["code"], "INVALID_ARGUMENT")
        self.assertIn("query", result["message"])


class RecommendBooksTest(unittest.TestCase):
    def _invoke(self, payload=None):
        return ApiTest.run_handler("recommend_books.py", payload)

    def test_recommend_default(self):
        result = self._invoke()
        self.assertEqual(result["count"], 5)
        self.assertEqual(len(result["books"]), 5)

    def test_recommend_by_category(self):
        result = self._invoke({"category": "科幻"})
        self.assertGreater(result["count"], 0)
        for b in result["books"]:
            self.assertEqual(b["category"], "科幻")

    def test_recommend_with_count(self):
        result = self._invoke({"count": 3})
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["books"]), 3)

    def test_recommend_bad_category(self):
        result = self._invoke({"category": "不存在"})
        self.assertEqual(result["phase"], "error")
        self.assertEqual(result["code"], "NO_MATCH")


if __name__ == "__main__":
    unittest.main()