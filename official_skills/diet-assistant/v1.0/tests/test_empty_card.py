"""空天不出卡：get_day / 删光当日只看被查询的那一天。

get_stats 仍看统计窗口：近 7 天有记录、只是今天没吃，统计洞察照常出卡。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import store  # noqa: E402
from diet_api import MODEL_VIEW_KEY, dispatch  # noqa: E402

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "_run.py")


class EmptyCardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_overrides = {
            "DIET_DATA_DIR": os.path.join(self.temp_dir.name, "archive"),
            "DIET_WORK_DIR": os.path.join(self.temp_dir.name, "work"),
        }
        self.previous_env = {k: os.environ.get(k) for k in self.env_overrides}
        os.environ.update(self.env_overrides)

    def tearDown(self) -> None:
        for key, previous in self.previous_env.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        self.temp_dir.cleanup()

    def _record(self, title: str, iso: str) -> dict:
        return dispatch({
            "operation": "record_meal", "title": title, "sceneOneliner": f"{title}。",
            "eatenAt": iso, "aiPrice": 18,
            "items": [{"name": "米饭", "portion": "一碗", "emoji": "🍚", "origin": "中国",
                       "kcal": 300, "protein_g": 10, "fat_g": 5, "carb_g": 40, "sodium_mg": 200}],
        })

    def assertNoCard(self, result: dict) -> None:
        self.assertEqual(set(result), {MODEL_VIEW_KEY}, "载荷应当被压掉，只剩模型视图")

    def assertHasCard(self, result: dict) -> None:
        self.assertIn("current_meal", result, "应当照常下发可渲染的载荷")

    def test_empty_archive_get_day_emits_no_card(self) -> None:
        result = dispatch({"operation": "get_day"})
        self.assertNoCard(result)
        self.assertEqual(result[MODEL_VIEW_KEY]["card_skipped"], "empty_day")
        self.assertTrue(result[MODEL_VIEW_KEY]["ok"], "不出卡不是失败，仍然是成功回执")

    def test_empty_archive_get_stats_emits_no_card(self) -> None:
        result = dispatch({"operation": "get_stats", "period": "week"})
        self.assertNoCard(result)
        self.assertEqual(result[MODEL_VIEW_KEY]["card_skipped"], "empty_archive")

    def test_recorded_meal_still_emits_card(self) -> None:
        self.assertHasCard(self._record("午餐", store.now_iso()))

    def test_day_with_meals_emits_card(self) -> None:
        self._record("午餐", store.now_iso())
        self.assertHasCard(dispatch({"operation": "get_day"}))

    def test_empty_today_skips_card_even_with_recent_history(self) -> None:
        """今天没吃：get_day 不出卡。近 7 天有记录也不例外——查的是今天。"""
        yesterday = (store.now() - timedelta(days=1)).strftime("%Y-%m-%dT12:30:00+08:00")
        self._record("昨天的午餐", yesterday)
        result = dispatch({"operation": "get_day"})
        self.assertNoCard(result)
        self.assertEqual(result[MODEL_VIEW_KEY]["card_skipped"], "empty_day")

    def test_get_stats_still_emits_when_today_empty_but_week_has_meals(self) -> None:
        """统计洞察看的是窗口，不是当天：今天没吃、昨天有记录，get_stats 照出。"""
        yesterday = (store.now() - timedelta(days=1)).strftime("%Y-%m-%dT12:30:00+08:00")
        self._record("昨天的午餐", yesterday)
        self.assertHasCard(dispatch({"operation": "get_stats", "period": "week"}))

    def test_history_outside_stats_window_emits_no_card(self) -> None:
        """只有 40 天前的记录：日/周窗口都落空，卡片上确实没东西可显示。"""
        old = (store.now() - timedelta(days=40)).strftime("%Y-%m-%dT12:30:00+08:00")
        self._record("上个月的午餐", old)
        self.assertNoCard(dispatch({"operation": "get_day"}))

    def test_deleting_the_last_meal_emits_no_card(self) -> None:
        meal_id = self._record("唯一一餐", store.now_iso())[MODEL_VIEW_KEY]["meal_id"]
        result = dispatch({"operation": "delete_meal", "mealId": meal_id})
        self.assertNoCard(result)
        self.assertEqual(result[MODEL_VIEW_KEY]["card_skipped"], "empty_day")

    def test_deleting_last_meal_of_that_day_skips_card_even_if_other_days_remain(self) -> None:
        yesterday = (store.now() - timedelta(days=1)).strftime("%Y-%m-%dT12:30:00+08:00")
        self._record("昨天的午餐", yesterday)
        meal_id = self._record("今天唯一一餐", store.now_iso())[MODEL_VIEW_KEY]["meal_id"]
        result = dispatch({"operation": "delete_meal", "mealId": meal_id})
        self.assertNoCard(result)
        self.assertEqual(result[MODEL_VIEW_KEY]["card_skipped"], "empty_day")

    def test_deleting_one_of_two_same_day_still_emits_card(self) -> None:
        first = self._record("午餐", store.now().strftime("%Y-%m-%dT12:30:00+08:00"))
        self._record("晚餐", store.now().strftime("%Y-%m-%dT19:00:00+08:00"))
        meal_id = first[MODEL_VIEW_KEY]["meal_id"]
        self.assertHasCard(dispatch({"operation": "delete_meal", "mealId": meal_id}))

    def test_runner_emits_no_sentinel_for_empty_archive(self) -> None:
        """端到端：不出卡意味着 stdout 只有一行，宿主中间件收不到 sentinel。"""
        proc = subprocess.Popen(
            [sys.executable, RUNNER, "show_app", json.dumps({"operation": "get_day"})],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            env=dict(os.environ, **self.env_overrides),
        )
        out, err = proc.communicate()
        self.assertEqual(proc.returncode, 0, err)
        lines = [line for line in out.split("\n") if line.strip()]
        self.assertEqual(len(lines), 1, f"应当只有正文一行，实际：{lines}")
        self.assertNotIn("__ONEAGENT_APP_RESULT__", out)
        self.assertTrue(json.loads(lines[0])["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
