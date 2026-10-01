"""领域 API 测试：经真实子进程调用 handler，顺带验证 stdout 恰好一行 JSON。

CLI 直接 json.loads(整段 stdout)，多打一行日志就会解析失败、UI 拿不到数据，
所以「恰好一行」是这个包最容易坏也最该被测住的不变量。
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
HANDLER = APP_ROOT / "scripts" / "daily_fortune.py"

PROFILE = {
    "version": "1.0",
    "profiles": {
        "self": {
            "key": "self",
            "relation": "self",
            "label": "本人",
            "gender": "male",
            "birth_date": "2000-02-02",
            "birth_time": "02:00",
            "birth_time_precision": "exact",
            "birth_place": "北京市朝阳区",
            "location": {
                "name": "北京市朝阳区",
                "longitude": 116.44355,
                "latitude": 39.9219,
                "timeZone": "Asia/Shanghai",
                "source": "seed-cn-admin-v1",
            },
            "confirmed": True,
            "missing": {},
            "history": [],
        }
    },
}


class ApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.profile_dir = root / "profile"
        self.profile_dir.mkdir()
        (self.profile_dir / "profiles.json").write_text(json.dumps(PROFILE), encoding="utf-8")
        self.empty_profile_dir = root / "empty-profile"
        self.empty_profile_dir.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def run_api(self, payload, profile_dir=None):
        env = dict(os.environ)
        env["METAPHYSICS_PROFILE_DIR"] = str(profile_dir or self.profile_dir)
        completed = subprocess.run(
            [sys.executable, str(HANDLER), json.dumps(payload)],
            capture_output=True,
            text=True,
            cwd=str(APP_ROOT),
            env=env,
            check=False,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"stdout 必须只有一行 JSON：{completed.stdout!r}{completed.stderr}")
        return json.loads(lines[0])

    def test_describe_lists_only_card_operations(self):
        result = self.run_api({"operation": "describe"})
        self.assertEqual(result["phase"], "result")
        operations = result["data"]["operations"]
        self.assertIn("get_card", operations)
        # 订阅能力已移除：契约里不该再出现任何订阅操作或频次。
        for removed in ["subscribe", "set_push_time", "unsubscribe", "list_subscriptions"]:
            self.assertNotIn(removed, operations)
        self.assertNotIn("frequencies", result["data"])
        self.assertNotIn("subscription", result["data"])

    def test_get_card_returns_full_snapshot(self):
        result = self.run_api({"operation": "get_card", "timekey": "today", "topickey": "wealth"})
        self.assertEqual(result["phase"], "result")
        data = result["data"]
        card = data["card"]
        for key in ["title", "summary", "score", "keyword", "overview", "lucky", "advice", "insight", "transit", "bazi"]:
            self.assertIn(key, card)
        self.assertTrue(45 <= card["score"]["value"] <= 88)
        # 快照里不再有订阅状态。
        self.assertNotIn("subscription", data)
        self.assertEqual(data["topickey"], "wealth")

    def test_time_dimensions_use_different_anchors(self):
        today = self.run_api({"operation": "get_card", "timekey": "today", "target_date": "2026-09-10"})
        week = self.run_api({"operation": "get_card", "timekey": "week", "target_date": "2026-09-10"})
        self.assertNotEqual(
            today["data"]["card"]["transit"]["anchorGanZhi"],
            week["data"]["card"]["transit"]["anchorGanZhi"],
            "today 与 week 的流期锚点相同，时间维度未区分",
        )

    def test_missing_profile_is_reported_not_raised(self):
        result = self.run_api({"operation": "get_card"}, profile_dir=self.empty_profile_dir)
        self.assertEqual(result["phase"], "result")
        self.assertTrue(result["data"]["needs_profile"])
        self.assertIsNone(result["data"]["card"])
        self.assertTrue(result["data"]["profile_message"])

    def test_removed_subscription_operations_are_rejected(self):
        # 订阅能力已整体移除：这些操作不能再被识别，避免界面或 Agent 调到半成品路径。
        for removed in ["subscribe", "set_push_time", "unsubscribe", "list_subscriptions"]:
            result = self.run_api({"operation": removed, "push_time": "07:30"})
            self.assertEqual(result["phase"], "error", removed)
            self.assertEqual(result["code"], "UNKNOWN_OPERATION", removed)

    def test_lucky_elements_track_the_period(self):
        # 回归：幸运色曾固定取日主之印，切今日/本周/本月/今年、换日期都不变。
        # 喜用必须随流期走，这里只断言"确实会变"，不断言具体取哪个五行。
        colors = {
            self.run_api({"operation": "get_card", "timekey": tk})["data"]["card"]["lucky"]["color"]
            for tk in ["today", "week", "month", "year"]
        }
        self.assertGreater(len(colors), 1, "四个时间维度的幸运色完全相同，喜用未随流期变化")

        by_date = {
            self.run_api({"operation": "get_card", "target_date": d})["data"]["card"]["lucky"]["color"]
            for d in ["2026-09-11", "2026-09-14", "2026-09-17", "2026-09-20", "2026-09-23", "2026-09-26"]
        }
        self.assertGreater(len(by_date), 1, "不同日期的幸运色完全相同，喜用未随日期变化")

    def test_lucky_fields_share_one_element(self):
        # 颜色/方位/数字/食物/配饰必须出自同一个五行，不能各算各的。
        row = {
            "木": ("青绿色", "东方", "3、8"), "火": ("暖红色", "南方", "2、7"),
            "土": ("米黄色", "中央", "5、0"), "金": ("白色", "西方", "4、9"),
            "水": ("深蓝色", "北方", "1、6"),
        }
        for tk in ["today", "week", "month", "year"]:
            card = self.run_api({"operation": "get_card", "timekey": tk})["data"]["card"]
            element = re.search(r"喜用取(.)：", card["evidence"][0]).group(1)
            color, direction, number = row[element]
            lucky = card["lucky"]
            self.assertTrue(lucky["color"].startswith(color), tk)
            self.assertEqual(lucky["direction"], direction, tk)
            self.assertEqual(lucky["number"], number, tk)

    def test_instance_id_is_echoed_when_provided(self):
        data = self.run_api({"operation": "get_card", "instanceId": "card-a1"})["data"]
        self.assertEqual(data["instanceId"], "card-a1")
        self.assertTrue(data["card"], "回显实例标识不应影响出卡")

    def test_instance_id_absent_by_default(self):
        # 宿主未下发时必须完全缺席，不能带空字段污染既有契约。
        data = self.run_api({"operation": "get_card"})["data"]
        self.assertNotIn("instanceId", data)

    def test_blank_instance_id_is_ignored(self):
        data = self.run_api({"operation": "get_card", "instanceId": "   "})["data"]
        self.assertNotIn("instanceId", data)

    def test_target_date_is_honored(self):
        result = self.run_api({"operation": "get_card", "target_date": "2026-10-01"})
        self.assertEqual(result["phase"], "result")
        self.assertEqual(result["data"]["target_date"], "2026-10-01")

    def test_unknown_operation_uses_stable_envelope(self):
        result = self.run_api({"operation": "no_such_operation"})
        self.assertEqual(result["phase"], "error")
        self.assertEqual(result["code"], "UNKNOWN_OPERATION")
        self.assertFalse(result["retryable"])


    def test_get_card_ships_all_16_combinations(self):
        """切换必须能在本地完成：16 种组合（4 时间维度 × 4 主题）随卡一次下发。"""
        data = self.run_api({"operation": "get_card"})["data"]
        cards = data.get("cards")
        self.assertIsInstance(cards, dict)
        self.assertEqual(sorted(cards.keys()), ["month", "today", "week", "year"])
        for tk, by_topic in cards.items():
            self.assertEqual(sorted(by_topic.keys()), ["career", "love", "social", "wealth"], tk)
            for topic, card in by_topic.items():
                self.assertIn("score", card, f"{tk}/{topic}")
                self.assertIn("insight", card, f"{tk}/{topic}")

    def test_precomputed_cards_vary_across_timekeys(self):
        """不同时间维度必须是不同的一张卡，否则切换看起来像没生效。"""
        cards = self.run_api({"operation": "get_card"})["data"]["cards"]
        anchors = {tk: cards[tk]["career"]["transit"]["anchorGanZhi"] for tk in cards}
        scores = {tk: cards[tk]["career"]["score"]["value"] for tk in cards}
        self.assertNotEqual(scores["today"], scores["week"], "今日与本周分数不应相同")
        self.assertNotEqual(anchors["today"], anchors["week"], "今日与本周锚点不应相同")

    def test_topics_change_only_the_insight(self):
        """主题只影响解读，幸运要素、指数、概述都必须保持不变。

        这是刻意的：幸运色等属于"本时段的气场"，与生活领域无关；
        领域差异只在解读区表达。切主题时若整卡都变，反而是回归缺陷。
        """
        cards = self.run_api({"operation": "get_card"})["data"]["cards"]
        for tk in cards:
            base = cards[tk]["career"]
            for topic in ("love", "wealth", "social"):
                other = cards[tk][topic]
                self.assertEqual(base["lucky"]["color"], other["lucky"]["color"], f"{tk}/{topic} 幸运色不应随主题变")
                self.assertEqual(base["lucky"]["time"], other["lucky"]["time"], f"{tk}/{topic} 幸运时段不应随主题变")
                self.assertEqual(base["score"]["value"], other["score"]["value"], f"{tk}/{topic} 指数不应随主题变")
                self.assertEqual(base["overview"], other["overview"], f"{tk}/{topic} 概述不应随主题变")
                self.assertNotEqual(base["insight"]["body"], other["insight"]["body"], f"{tk}/{topic} 解读应随主题变")

    def test_lucky_elements_change_with_timekey_only(self):
        """幸运色只随时间段变化：同段内四个主题一致，四个时段互不相同。"""
        cards = self.run_api({"operation": "get_card"})["data"]["cards"]
        timekeys = list(cards)
        topics = list(cards[timekeys[0]])
        for tk in timekeys:
            colors = {cards[tk][tp]["lucky"]["color"] for tp in topics}
            self.assertEqual(len(colors), 1, f"{tk} 时段内幸运色应一致，实际 {colors}")
        period_colors = [cards[tk]["career"]["lucky"]["color"] for tk in timekeys]
        self.assertEqual(len(set(period_colors)), len(timekeys), f"四个时段应不同色：{period_colors}")

    def test_all_sixteen_insights_are_distinct(self):
        """16 种组合的解读正文必须各不相同；概述则只有 4 种（只随时段）。"""
        cards = self.run_api({"operation": "get_card"})["data"]["cards"]
        overviews, bodies = set(), set()
        for tk in cards:
            for tp in cards[tk]:
                overviews.add(cards[tk][tp]["overview"])
                bodies.add(cards[tk][tp]["insight"]["body"])
        self.assertEqual(len(overviews), 4, "概述应只随 4 个时段变化")
        self.assertEqual(len(bodies), 16, "解读正文应 16 种")

    def test_topic_star_is_exposed(self):
        """卡片要暴露该领域对应的十神，供界面与调试核对。"""
        cards = self.run_api({"operation": "get_card"})["data"]["cards"]
        for tk in cards:
            self.assertIn("topicStar", cards[tk]["career"]["transit"], tk)
            self.assertIn("topicRelation", cards[tk]["career"]["transit"], tk)
        # 女命事业与感情同看官杀，但解读必须不同（靠辅星食伤区分）
        self.assertNotEqual(
            cards["today"]["career"]["insight"]["body"],
            cards["today"]["love"]["insight"]["body"]
        )

    def test_describe_does_not_ship_cards(self):
        result = self.run_api({"operation": "describe"})
        self.assertEqual(result["phase"], "result")
        self.assertNotIn("cards", result["data"])


if __name__ == "__main__":
    unittest.main()
