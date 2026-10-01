#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import nutrition  # noqa: E402
from a2ui import FALLBACK_PHOTO_URL  # noqa: E402
from cli_contract import ContractError, validate  # noqa: E402
from diet_api import MODEL_VIEW_KEY, dispatch, resolve_eaten_at  # noqa: E402
from payload_schema import PayloadValidationError, validate_payload  # noqa: E402
from store import now as store_now  # noqa: E402
import store  # noqa: E402


class PayloadSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        # 存档目录和本地工作目录都要指到临时区，否则用例之间会共用 /tmp 里那份库
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

    def test_eaten_at_defaults_to_upload_time(self) -> None:
        now = store_now()
        self.assertEqual(resolve_eaten_at(None).hour, now.hour)
        self.assertEqual(resolve_eaten_at("").hour, now.hour)

    def test_eaten_at_honours_explicit_time(self) -> None:
        when = resolve_eaten_at("2026-09-03T08:15:00+08:00")
        self.assertEqual((when.strftime("%Y-%m-%d"), when.hour, when.minute),
                         ("2026-09-03", 8, 15))

    def test_date_without_clock_keeps_date_and_borrows_now(self) -> None:
        """只给日期不能落到 00:00，否则餐次会被判成夜宵。"""
        now = store_now()
        when = resolve_eaten_at("2026-09-03")
        self.assertEqual(when.strftime("%Y-%m-%d"), "2026-09-03")
        self.assertEqual((when.hour, when.minute), (now.hour, now.minute))

    def test_day_summary_carries_eaten_at(self) -> None:
        dispatch({
            "operation": "record_meal",
            "title": "带时间的一餐",
            "sceneOneliner": "验证摘要里有 eaten_at。",
            "eatenAt": "2026-09-03T08:15:00+08:00",
            "aiPrice": 18,
            "items": [{"name": "燕麦", "portion": "一碗", "emoji": "🥣", "origin": "中国",
                       "kcal": 300, "protein_g": 10, "fat_g": 5, "carb_g": 50, "sodium_mg": 100}],
        })
        result = dispatch({"operation": "get_day", "date": "2026-09-03"})
        result.pop(MODEL_VIEW_KEY)
        validate_payload(result)
        summaries = [m for v in result["today"]["meals_by_type"].values() for m in v]
        self.assertEqual([m["eaten_at"] for m in summaries], ["2026-09-03T08:15:00+08:00"])

    def _record(self, title: str, iso: str, kcal: int = 300) -> dict:
        return dispatch({
            "operation": "record_meal", "title": title, "sceneOneliner": f"{title}。",
            "eatenAt": iso, "aiPrice": 18,
            "items": [{"name": "米饭", "portion": "一碗", "emoji": "🍚", "origin": "中国",
                       "kcal": kcal, "protein_g": 10, "fat_g": 5, "carb_g": 40, "sodium_mg": 200}],
        })

    def test_day_regularity_uses_trailing_week(self) -> None:
        """规律性看跨天离散：只喂当天永远不够两天样本，得按最近 7 天算。"""
        for day in ("2026-09-02", "2026-09-03", "2026-09-04"):
            self._record(f"早餐 {day}", f"{day}T08:{day[-1]}0:00+08:00")
            self._record(f"午餐 {day}", f"{day}T12:{day[-1]}0:00+08:00")
        result = dispatch({"operation": "get_stats", "period": "day", "date": "2026-09-04"})
        result.pop(MODEL_VIEW_KEY)
        validate_payload(result)
        day = result["stats"]["day"]
        self.assertIsNotNone(day["regularity_score"])
        self.assertEqual(day["meal_count"], 2)  # 摘要仍然只算当天

    def test_single_meal_falls_back_to_default_regularity(self) -> None:
        """只有一顿：算不出离散度，卡片上那个圈不能空着，给 DEFAULT_REGULARITY。"""
        self._record("午餐", "2026-09-08T12:45:00+08:00")
        result = dispatch({"operation": "get_stats", "period": "week", "date": "2026-09-08"})
        result.pop(MODEL_VIEW_KEY)
        validate_payload(result)
        for period in ("day", "week"):
            with self.subTest(period=period):
                self.assertEqual(
                    result["stats"][period]["regularity_score"], nutrition.DEFAULT_REGULARITY
                )

    def test_real_spread_scores_below_default(self) -> None:
        """兜底值不能盖掉真实分数：作息飘 3 小时得明显低于 99，否则这个分就白算了。"""
        # 都落在早餐窗（05:00–11:00）内才进得了正餐桶，但彼此拉开 2 小时
        for day, hour in (("2026-09-02", "06"), ("2026-09-03", "08"), ("2026-09-04", "10")):
            self._record(f"早餐 {day}", f"{day}T{hour}:00:00+08:00")
        result = dispatch({"operation": "get_stats", "period": "week", "date": "2026-09-04"})
        result.pop(MODEL_VIEW_KEY)
        validate_payload(result)
        score = result["stats"]["week"]["regularity_score"]
        self.assertLess(score, nutrition.DEFAULT_REGULARITY)

    def test_null_regularity_is_rejected_by_schema(self) -> None:
        """兜底之后 null 不该再出现；漏一个过去就是卡片开天窗，schema 得挡住。"""
        self._record("午餐", "2026-09-08T12:45:00+08:00")
        result = dispatch({"operation": "get_stats", "period": "week", "date": "2026-09-08"})
        result.pop(MODEL_VIEW_KEY)
        result["stats"]["week"]["regularity_score"] = None
        with self.assertRaises(PayloadValidationError):
            validate_payload(result)

    def test_week_average_divides_by_days_with_records(self) -> None:
        self._record("唯一一餐", "2026-09-04T08:30:00+08:00", kcal=1180)
        result = dispatch({"operation": "get_stats", "period": "week", "date": "2026-09-04"})
        result.pop(MODEL_VIEW_KEY)
        week = result["stats"]["week"]
        self.assertEqual(week["meal_count"], 1)
        self.assertEqual(week["avg"]["kcal"], 1180)  # 不是 1180/7

    def test_day_and_week_nutrient_avgs_are_integers(self) -> None:
        """日/周摘要与本餐 totals 统一取整，避免日纬 124.5、周纬 124 这种位数不一致。"""
        result = dispatch({
            "operation": "record_meal",
            "title": "小数餐",
            "sceneOneliner": "测试",
            "mealType": "dinner",
            "eatenAt": "2026-09-04T19:00:00+08:00",
            "aiPrice": 20,
            "items": [{
                "name": "A", "portion": "一份", "emoji": "🍜", "origin": "测试",
                "kcal": 100.4, "protein_g": 12.4, "fat_g": 7.6, "carb_g": 20.2, "sodium_mg": 100.9,
            }, {
                "name": "B", "portion": "一份", "emoji": "🍚", "origin": "测试",
                "kcal": 50.3, "protein_g": 3.3, "fat_g": 1.2, "carb_g": 10.1, "sodium_mg": 50.1,
            }],
        })
        totals = result["current_meal"]["totals"]
        for key in ("kcal", "protein_g", "fat_g", "carb_g", "sodium_mg"):
            self.assertIsInstance(totals[key], int, f"totals.{key}={totals[key]!r}")
        # 100.4+50.3 → 151；12.4+3.3 → 16；7.6+1.2 → 9；20.2+10.1 → 30；100.9+50.1 → 151
        self.assertEqual(totals["kcal"], 151)
        self.assertEqual(totals["protein_g"], 16)
        self.assertEqual(totals["fat_g"], 9)
        self.assertEqual(totals["carb_g"], 30)
        self.assertEqual(totals["sodium_mg"], 151)

        day = dispatch({"operation": "get_stats", "period": "day", "date": "2026-09-04"})["stats"]["day"]
        week = dispatch({"operation": "get_stats", "period": "week", "date": "2026-09-04"})["stats"]["week"]
        for label, avg in (("day", day["avg"]), ("week", week["avg"])):
            for key, value in avg.items():
                self.assertIsInstance(value, int, f"{label}.avg.{key}={value!r}")

    def test_record_receipt_has_no_user_facing_receipt_string(self) -> None:
        result = self._record("午餐", "2026-09-02T12:30:00+08:00")
        model = result[MODEL_VIEW_KEY]
        self.assertNotIn("receipt", model)
        self.assertTrue(model.get("saved"))
        self.assertTrue(model.get("meal_id"))

    def _record_photo(self, title: str, photo: str, iso: str) -> dict:
        return dispatch({
            "operation": "record_meal", "title": title, "sceneOneliner": f"{title}。",
            "mealType": "midnight", "eatenAt": iso, "photoUrl": photo, "aiPrice": 10,
            "items": [{"name": title, "portion": "一份", "emoji": "🍜", "origin": "中国",
                       "kcal": 200, "protein_g": 5, "fat_g": 5, "carb_g": 20, "sodium_mg": 100}],
        })

    def test_same_slot_bars_get_ordinal_labels(self) -> None:
        """同槽多卡后一天两顿夜宵，两根柱子都叫「夜宵」在图上分不出谁是谁。"""
        self._record_photo("酸奶", "http://a/1", "2026-09-09T00:40:00+08:00")
        second = self._record_photo("辣条", "http://a/2", "2026-09-09T00:41:00+08:00")
        day = second["stats"]["day"]
        self.assertEqual(day["trend_labels"], ["夜宵①", "夜宵②"])
        self.assertEqual([c["date"] for c in day["nutrition_composition"]], ["夜宵①", "夜宵②"])
        # 序号跟着用餐时刻走，跟柱高一一对应，不能各排各的
        self.assertEqual(day["daily_kcal_trend"], [200, 200])
        second.pop(MODEL_VIEW_KEY)
        validate_payload(second)

    def test_lone_meal_keeps_plain_label(self) -> None:
        """一天就一顿的餐次不加序号：绝大多数情况如此，无谓的「①」纯属噪声。"""
        only = self._record_photo("酸奶", "http://a/1", "2026-09-09T00:40:00+08:00")
        self.assertEqual(only["stats"]["day"]["trend_labels"], ["夜宵"])

    def test_ordinals_are_per_meal_type(self) -> None:
        """序号按餐次各自数：午餐两条编①②，同日唯一的一顿夜宵仍是光板。

        餐次名全站一个写法，图表里也是「午餐」而不是缩写的「午」。
        """
        for iso, name in [("2026-09-09T12:00:00+08:00", "盖饭"),
                          ("2026-09-09T12:30:00+08:00", "酸奶")]:
            payload = dispatch({
                "operation": "record_meal", "title": name, "sceneOneliner": f"{name}。",
                "mealType": "lunch", "eatenAt": iso, "aiPrice": 10,
                "items": [{"name": name, "portion": "一份", "emoji": "🍚", "origin": "中国",
                           "kcal": 100, "protein_g": 5, "fat_g": 5, "carb_g": 10, "sodium_mg": 10}],
            })
        payload = self._record_photo("辣条", "http://a/3", "2026-09-09T23:00:00+08:00")
        self.assertEqual(payload["stats"]["day"]["trend_labels"], ["午餐①", "午餐②", "夜宵"])

    def test_reused_photo_across_same_day_meals_warns(self) -> None:
        """同槽补记时模型容易把上一餐的短链抄下来，卡片就配上别的东西的照片。

        真实事故：夜宵先记酸奶、再补辣条，两条 photoUrl 都是酸奶那条短链。
        落库、校验、出卡全都正常，没有任何地方会报错——只能靠这条告警。
        """
        same = "http://yb-test.woa.com/EJxFkq4XBa0"
        first = self._record_photo("酸奶", same, "2026-09-09T00:40:00+08:00")
        self.assertNotIn("photo_warning", first[MODEL_VIEW_KEY], "第一条没得撞，不该告警")

        second = self._record_photo("辣条", same, "2026-09-09T00:41:00+08:00")
        warning = second[MODEL_VIEW_KEY].get("photo_warning")
        self.assertIsNotNone(warning, "同一天两条共用一张图必须告警")
        self.assertIn("酸奶", warning, "要点名撞的是哪一条，否则模型不知道去改谁")
        self.assertIn(second[MODEL_VIEW_KEY]["meal_id"], warning, "要给出能直接改的 meal_id")
        # 告警不拦截：记录照样落库、卡片照样出
        self.assertTrue(second[MODEL_VIEW_KEY]["saved"])
        second.pop(MODEL_VIEW_KEY)
        validate_payload(second)

    def test_distinct_photos_do_not_warn(self) -> None:
        """抄对了就别吵：两张不同的图是同槽多卡的正常形态，告警多了就没人看了。"""
        self._record_photo("酸奶", "http://yb-test.woa.com/EJxFkq4XBa0", "2026-09-09T00:40:00+08:00")
        second = self._record_photo("辣条", "http://yb-test.woa.com/CTOSFv9GJST", "2026-09-09T00:41:00+08:00")
        self.assertNotIn("photo_warning", second[MODEL_VIEW_KEY])

    def test_same_photo_on_different_days_does_not_warn(self) -> None:
        """判据限定在同一天：隔天重复用图更可能是真的又吃了一样的东西，不该吵。"""
        same = "http://yb-test.woa.com/EJxFkq4XBa0"
        self._record_photo("夜宵", same, "2026-09-08T23:00:00+08:00")
        second = self._record_photo("夜宵", same, "2026-09-09T23:00:00+08:00")
        self.assertNotIn("photo_warning", second[MODEL_VIEW_KEY])

    def test_same_slot_keeps_independent_cards(self) -> None:
        """同槽多卡：午餐记两次是两条独立记录，各有图、标题、营养，不合并。"""
        first = dispatch({
            "operation": "record_meal",
            "title": "一勺卤汁浇透的米饭",
            "sceneOneliner": "第一张",
            "mealType": "lunch",
            "eatenAt": "2026-09-04T12:00:00+08:00",
            "photoUrl": "https://example.com/old.jpg",
            "aiPrice": 20,
            "items": [{"name": "米饭", "portion": "一碗", "emoji": "🍚", "origin": "中国",
                       "kcal": 200, "protein_g": 5, "fat_g": 1, "carb_g": 40, "sodium_mg": 10}],
        })
        second = dispatch({
            "operation": "record_meal",
            "title": "午后那颗苹果",
            "sceneOneliner": "补一张",
            "mealType": "lunch",
            "eatenAt": "2026-09-04T12:30:00+08:00",
            "photoUrl": "https://example.com/new.jpg",
            "aiPrice": 8,
            "narrative": {"care": "第二张卡自己的分析。"},
            "items": [{"name": "苹果", "portion": "一个", "emoji": "🍎", "origin": "中国",
                       "kcal": 50, "protein_g": 0, "fat_g": 0, "carb_g": 14, "sodium_mg": 1}],
        })
        self.assertNotEqual(
            first[MODEL_VIEW_KEY]["meal_id"], second[MODEL_VIEW_KEY]["meal_id"],
            "同槽补记必须换 meal_id，不能盖掉第一条",
        )
        self.assertNotIn("merged", second[MODEL_VIEW_KEY])

        day = dispatch({"operation": "get_day", "date": "2026-09-04"})
        day.pop(MODEL_VIEW_KEY)
        validate_payload(day)
        lunches = day["today"]["meals_by_type"]["lunch"]
        self.assertEqual(len(lunches), 2)
        by_id = {m["meal_id"]: m for m in lunches}
        self.assertEqual(by_id[first["current_meal"]["meal_id"]]["photo_url"],
                         "https://example.com/old.jpg")
        self.assertEqual(by_id[second["current_meal"]["meal_id"]]["photo_url"],
                         "https://example.com/new.jpg")
        self.assertEqual(by_id[first["current_meal"]["meal_id"]]["totals"]["kcal"], 200)
        self.assertEqual(by_id[second["current_meal"]["meal_id"]]["totals"]["kcal"], 50)
        # 今日合计是两张卡相加，不是互相覆盖
        self.assertEqual(day["today"]["totals"]["kcal"], 250)

    def test_same_day_same_type_second_record_is_new_card(self) -> None:
        """同天同餐次第二次记录：标题/时间/热量都属于新卡，旧卡原样留着。"""
        first = self._record("早餐一", "2026-09-04T07:00:00+08:00", kcal=300)
        second = self._record("早餐二", "2026-09-04T09:00:00+08:00", kcal=100)
        self.assertEqual(second["current_meal"]["title"], "早餐二")
        self.assertEqual(second["current_meal"]["eaten_at"], "2026-09-04T09:00:00+08:00")
        self.assertEqual(round(second["current_meal"]["totals"]["kcal"]), 100)
        self.assertNotEqual(
            first[MODEL_VIEW_KEY]["meal_id"], second[MODEL_VIEW_KEY]["meal_id"],
        )
        day = dispatch({"operation": "get_day", "date": "2026-09-04"})
        day.pop(MODEL_VIEW_KEY)
        self.assertEqual(len(day["today"]["meals_by_type"]["breakfast"]), 2)
        self.assertEqual(day["today"]["totals"]["kcal"], 400)

    def test_explicit_meal_type_wins_over_clock_window(self) -> None:
        """用户明确说「这是夜宵」时，即使钟点在午餐窗也归夜宵槽。"""
        result = dispatch({
            "operation": "record_meal",
            "title": "补一顿",
            "sceneOneliner": "用户说是夜宵",
            "mealType": "midnight",
            "eatenAt": "2026-09-04T12:00:00+08:00",
            "eatenAtSource": "user",
            "aiPrice": 18,
            "items": [{"name": "泡面", "portion": "一碗", "emoji": "🍜", "origin": "中国",
                       "kcal": 400, "protein_g": 10, "fat_g": 15, "carb_g": 50, "sodium_mg": 800}],
        })
        self.assertEqual(result["current_meal"]["meal_type"], "midnight")

    def test_generated_shared_payload_is_valid(self) -> None:
        # 得先有一餐：档案空的时候 get_day 刻意不出卡，拿不到可校验的载荷
        self._record("午餐", "2026-09-02T12:30:00+08:00")
        result = dispatch({"operation": "get_day", "date": "2026-09-02"})
        model_view = result.pop(MODEL_VIEW_KEY)
        self.assertTrue(model_view["ok"])
        self.assertIs(validate_payload(result), result)

    def test_unknown_render_key_is_rejected(self) -> None:
        self._record("午餐", "2026-09-02T12:30:00+08:00")
        result = dispatch({"operation": "get_day", "date": "2026-09-02"})
        result.pop(MODEL_VIEW_KEY)
        invalid = copy.deepcopy(result)
        invalid["surprise"] = True
        with self.assertRaisesRegex(PayloadValidationError, "未知字段"):
            validate_payload(invalid)

    def test_model_input_types_and_unknown_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "未知参数"):
            validate("get_day", {"operation": "get_day", "unexpected": 1})
        with self.assertRaisesRegex(ContractError, "必须是数字"):
            validate("record_meal", {
                "operation": "record_meal",
                "title": "午餐",
                "sceneOneliner": "测试",
                "aiPrice": 18,
                "items": [{
                    "name": "米饭",
                    "portion": "一碗",
                    "emoji": "🍚",
                    "origin": "中国",
                    "kcal": "200",
                    "protein_g": 4,
                    "fat_g": 1,
                    "carb_g": 44,
                    "sodium_mg": 2,
                }],
            })

    def test_runner_does_not_emit_app_result_for_invalid_payload(self) -> None:
        request = {
            "operation": "record_meal",
            "title": "午餐",
            "sceneOneliner": "测试",
            "aiPrice": 18,
            "items": [{
                "name": "米饭",
                "portion": "一碗",
                "emoji": "🍚",
                "origin": "中国",
                "kcal": "200",
                "protein_g": 4,
                "fat_g": 1,
                "carb_g": 44,
                "sodium_mg": 2,
            }],
        }
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "_run.py"), "show_app", json.dumps(request, ensure_ascii=False)],
            capture_output=True,
            text=True,
            env={**os.environ, **self.env_overrides},
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("__ONEAGENT_APP_RESULT__", completed.stdout)
        self.assertEqual(json.loads(completed.stdout)["code"], "invalid_argument")

    # ---- 测算（estimate_meal）与纯文字记录 ----

    # 25×4 + 10×9 + 30×4 = 310，跟 kcal 对齐，交叉核验零偏差
    ESTIMATE_ITEM = {
        "name": "番茄炒蛋", "portion": "一盘", "emoji": "🍅", "origin": "中国",
        "kcal": 310, "protein_g": 25, "fat_g": 10, "carb_g": 30, "sodium_mg": 400,
    }
    ESTIMATE_NARRATIVE = {
        "care": "番茄提供茄红素，鸡蛋补优质蛋白；整盘约 310 kcal，油脂主要来自炒制，适量即可。",
    }
    ESTIMATE_TITLE = "一盘番茄红配蛋黄"
    ESTIMATE_SCENE = "番茄炒蛋刚出锅，汁水还在盘底晃。"

    def test_estimate_computes_totals_and_emits_card(self) -> None:
        result = dispatch({
            "operation": "estimate_meal", "aiPrice": 22,
            "items": [self.ESTIMATE_ITEM], "narrative": self.ESTIMATE_NARRATIVE,
            "title": self.ESTIMATE_TITLE, "sceneOneliner": self.ESTIMATE_SCENE,
        })
        model = result.pop(MODEL_VIEW_KEY)
        self.assertFalse(model["saved"])
        self.assertEqual(model["totals"]["kcal"], 310)
        self.assertEqual(model["delta_pct"], 0)
        self.assertTrue(model["cross_check_passed"])
        validate_payload(result)
        self.assertEqual(result["current_meal"]["title"], self.ESTIMATE_TITLE)
        self.assertEqual(result["current_meal"]["scene_oneliner"], self.ESTIMATE_SCENE)
        self.assertEqual(result["current_meal"]["meal_id"], "m_estimate")
        self.assertEqual(result["current_meal"]["ai_price"], 22)
        self.assertEqual(result["current_meal"]["totals"]["ai_price"], 22)
        self.assertEqual(result["current_meal"]["narrative"]["care"], self.ESTIMATE_NARRATIVE["care"])

    def test_estimate_leaves_archive_untouched(self) -> None:
        """测算算的是用户没吃的东西，混进今日食书就等于替他记了一餐。"""
        dispatch({
            "operation": "estimate_meal", "aiPrice": 22,
            "items": [self.ESTIMATE_ITEM], "narrative": self.ESTIMATE_NARRATIVE,
            "title": self.ESTIMATE_TITLE, "sceneOneliner": self.ESTIMATE_SCENE,
        })
        day = dispatch({"operation": "get_day"})
        self.assertEqual(day[MODEL_VIEW_KEY]["meals"], [])
        self.assertEqual(day[MODEL_VIEW_KEY]["totals"]["kcal"], 0)

    def test_estimate_rejects_record_only_fields(self) -> None:
        """eatenAt / mealType 属于落库，测算传了要当参数错误挡掉。"""
        with self.assertRaises(ContractError) as caught:
            validate("estimate_meal", {
                "operation": "estimate_meal",
                "aiPrice": 22,
                "items": [self.ESTIMATE_ITEM],
                "narrative": self.ESTIMATE_NARRATIVE,
                "eatenAt": "2026-09-03T12:00:00+08:00",
            })
        self.assertEqual(caught.exception.code, "invalid_argument")

    def test_estimate_requires_care_for_card_analysis(self) -> None:
        """卡片「本餐营养学分析」绑 narrative.care，测算缺了必须挡下。"""
        with self.assertRaises(ContractError) as caught:
            validate("estimate_meal", {
                "operation": "estimate_meal",
                "aiPrice": 22,
                "items": [self.ESTIMATE_ITEM],
                "title": self.ESTIMATE_TITLE,
                "sceneOneliner": self.ESTIMATE_SCENE,
            })
        self.assertEqual(caught.exception.code, "missing_argument")
        with self.assertRaises(ContractError) as caught:
            validate("estimate_meal", {
                "operation": "estimate_meal",
                "aiPrice": 22,
                "items": [self.ESTIMATE_ITEM],
                "title": self.ESTIMATE_TITLE,
                "sceneOneliner": self.ESTIMATE_SCENE,
                "narrative": {"care": "   "},
            })
        self.assertEqual(caught.exception.code, "missing_argument")
        self.assertIn("care", str(caught.exception))

    def test_estimate_requires_own_title_and_scene(self) -> None:
        """测算也出卡。缺了只能由脚本兜底，而脚本编得出的只有「测算：番茄炒蛋」这种菜单名。"""
        with self.assertRaises(ContractError) as caught:
            validate("estimate_meal", {
                "operation": "estimate_meal",
                "aiPrice": 22,
                "items": [self.ESTIMATE_ITEM],
                "narrative": self.ESTIMATE_NARRATIVE,
            })
        self.assertEqual(caught.exception.code, "missing_argument")
        self.assertIn("title", str(caught.exception))
        self.assertIn("sceneOneliner", str(caught.exception))

    def test_long_portion_is_rejected(self) -> None:
        """portion 直接上卡片那一栏，写成一句话会挤坏版式，契约层就得挡住。"""
        item = {**self.ESTIMATE_ITEM, "portion": "约250g（生重约300g，去骨切块）"}
        with self.assertRaises(ContractError) as caught:
            validate("record_meal", {
                "operation": "record_meal",
                "title": "夜灯下的油炸时光",
                "sceneOneliner": "刚吃完。",
                "aiPrice": 18,
                "items": [item],
            })
        self.assertEqual(caught.exception.code, "invalid_argument")
        self.assertIn("assumptions", str(caught.exception), "报错要指出克重该写去哪")

    def _validate_portion(self, portion: str) -> None:
        validate("record_meal", {
            "operation": "record_meal",
            "title": "夜灯下的油炸时光",
            "sceneOneliner": "刚吃完。",
            "aiPrice": 18,
            "items": [{**self.ESTIMATE_ITEM, "portion": portion}],
        })

    def test_serving_unit_portion_passes(self) -> None:
        for portion in (
            "1个", "一个", "1份", "一份", "半份", "一碗", "1杯", "两块", "2块",
            "一盘", "一小把", "一勺", "半包", "一根", "一片", "三只",
            "二两",         # 中文里本来就当份量用，不是在报重量
        ):
            with self.subTest(portion=portion):
                self._validate_portion(portion)

    def test_portion_length_boundary(self) -> None:
        """3 个字是上限本身，第 4 个字就得退。卡片右栏放不下更多。"""
        self._validate_portion("一小把")
        with self.assertRaises(ContractError) as caught:
            self._validate_portion("一大汤勺")
        self.assertEqual(caught.exception.code, "invalid_argument")

    def test_parenthesized_gram_portion_is_rejected(self) -> None:
        """「半包（50g）」份量在前、克重只是括号补充，但括号也算字数，7 字照退。

        上限还是 10 字的时候这条是放行的，收到 3 字之后就没有豁免了——
        想保留克重信息就写 `半包` 并把 `50g` 挪进 assumptions。
        """
        with self.assertRaises(ContractError) as caught:
            self._validate_portion("半包（50g）")
        self.assertEqual(caught.exception.code, "invalid_argument")
        message = str(caught.exception)
        self.assertIn("半包（50g）", message, "报错要带上原值，方便定位")
        self.assertIn("assumptions", message, "报错要指出克重该写去哪")

    def test_pure_measure_portion_is_rejected(self) -> None:
        """整串就是「数字+克/毫升」的是计量不是份量，长度合规也要挡。"""
        for portion in ("约250g", "250g", "250克", "150ml", "150毫升", "1.5kg", "200-250g"):
            with self.subTest(portion=portion):
                with self.assertRaises(ContractError) as caught:
                    self._validate_portion(portion)
                self.assertEqual(caught.exception.code, "invalid_argument")
                message = str(caught.exception)
                self.assertIn("assumptions", message, "报错要指出克重该写去哪")
                self.assertIn(portion, message, "报错要带上原值，方便定位")

    def _record_with_title(self, title: str) -> dict:
        return dispatch({
            "operation": "record_meal",
            "title": title,
            "sceneOneliner": "刚吃完，汤都喝干净了。",
            "aiPrice": 18,
            "items": [self.ESTIMATE_ITEM],
        })

    def test_menu_name_title_is_rejected(self) -> None:
        """标题挂餐次/操作前缀就是菜单名。餐次已在卡片时间行，重复写一遍白占 40 字。"""
        for title in ("午餐：牛肉面加卤蛋", "夜宵：鲍师傅海苔小贝", "午餐 · 牛肉面",
                      "测算：番茄炒蛋", "今日｜早餐", "晚饭:炒饭"):
            with self.subTest(title=title):
                with self.assertRaises(ContractError) as caught:
                    self._record_with_title(title)
                self.assertEqual(caught.exception.code, "invalid_argument")
                message = str(caught.exception)
                self.assertIn(title, message, "报错要带上原值，方便定位")
                self.assertIn("一碗热气里的牛骨香", message, "报错要给出能照着写的正例")

    def test_scenic_title_passes(self) -> None:
        """守卫只认「前缀+分隔符」这一个机械信号，不去判够不够有画面，别误伤。

        「午后那杯冰美式」以「午」开头但不是餐次前缀，「记一笔热汤」含「记」但没有分隔符，
        这两条最容易被写宽的正则咬到。
        """
        for title in ("一碗热气里的牛骨香", "夜灯下的油炸时光", "只收一颗的海苔小贝",
                      "午后那杯冰美式", "记一笔热汤"):
            with self.subTest(title=title):
                result = self._record_with_title(title)
                self.assertEqual(result["current_meal"]["title"], title)

    def test_menu_name_title_is_rejected_in_patch(self) -> None:
        """改标题跟记标题走同一把尺子，不然从 update_meal 绕一下就进来了。"""
        meal_id = self._record_with_title("一碗热气里的牛骨香").pop(MODEL_VIEW_KEY)["meal_id"]
        with self.assertRaises(ContractError) as caught:
            dispatch({
                "operation": "update_meal",
                "mealId": meal_id,
                "patch": {"title": "午餐：牛肉面加卤蛋"},
            })
        self.assertEqual(caught.exception.code, "invalid_argument")

    def test_meal_labels_have_one_source(self) -> None:
        """餐次中文名以前 diet_api / a2ui / nutrition 各抄一份，加一个餐次要改四处。"""
        import a2ui
        import nutrition
        import store

        self.assertIs(a2ui.MEAL_LABEL, store.MEAL_LABEL)
        self.assertIs(nutrition.MEAL_LABEL, store.MEAL_LABEL)
        self.assertEqual(set(store.MEAL_LABEL), set(store.MEAL_TYPES))
        self.assertFalse(hasattr(store, "MEAL_SHORT_LABEL"),
                         "单字缩写表已删：同一餐次不该卡片叫「午餐」、图表叫「午」")

    def test_record_meal_accepts_text_only_entry(self) -> None:
        """纯文字记录没有照片是正常的：档案里 null，出卡填兜底图、角标「无图」。"""
        result = dispatch({
            "operation": "record_meal",
            "title": "一碗拉面",
            "sceneOneliner": "刚吃完，汤都喝干净了。",
            "aiPrice": 18,
            "items": [self.ESTIMATE_ITEM],
        })
        model = result.pop(MODEL_VIEW_KEY)
        validate_payload(result)
        self.assertTrue(model["meal_id"])
        self.assertEqual(result["current_meal"]["photo_url"], FALLBACK_PHOTO_URL)
        self.assertEqual(result["current_meal"]["photo_badge"], "无图")
        stored = store.find_meal(model["meal_id"])
        self.assertIsNone(stored["photo_url"], "兜底图只出卡，不回写档案")
        found = None
        for rows in result["today"]["meals_by_type"].values():
            for row in rows:
                if row["meal_id"] == model["meal_id"]:
                    found = row
        self.assertIsNotNone(found)
        self.assertEqual(found["photo_url"], FALLBACK_PHOTO_URL)
        self.assertNotIn("photo_badge", found, "今日食书摘要没有 photo_badge 字段")

    def test_rejects_data_uri_photo_as_missing(self) -> None:
        """旧版会把缺图填成 data:image/svg；现在这种值也当成没图，出卡走兜底。"""
        result = dispatch({
            "operation": "record_meal",
            "title": "一碗拉面",
            "sceneOneliner": "刚吃完。",
            "aiPrice": 18,
            "photoUrl": "data:image/svg+xml;charset=utf-8,fake",
            "items": [self.ESTIMATE_ITEM],
        })
        model = result.pop(MODEL_VIEW_KEY)
        validate_payload(result)
        self.assertEqual(result["current_meal"]["photo_url"], FALLBACK_PHOTO_URL)
        self.assertEqual(result["current_meal"]["photo_badge"], "无图")
        # 档案原样留着这份非法值，出卡时再当成没图。不在写入路径上改写用户字段。
        self.assertEqual(
            store.find_meal(model["meal_id"])["photo_url"],
            "data:image/svg+xml;charset=utf-8,fake",
        )

    def test_record_meal_keeps_http_photo_and_marks_live(self) -> None:
        result = dispatch({
            "operation": "record_meal",
            "title": "一碗拉面",
            "sceneOneliner": "刚吃完，汤都喝干净了。",
            "photoUrl": "https://example.com/ramen.jpg",
            "aiPrice": 18,
            "items": [self.ESTIMATE_ITEM],
        })
        result.pop(MODEL_VIEW_KEY)
        validate_payload(result)
        self.assertEqual(result["current_meal"]["photo_url"], "https://example.com/ramen.jpg")
        self.assertEqual(result["current_meal"]["photo_badge"], "实拍")

    def test_runner_emits_app_result_for_estimate(self) -> None:
        """测算不落库，但调用了技能就要出卡，sentinel 必须在。"""
        request = {
            "operation": "estimate_meal", "aiPrice": 22,
            "items": [self.ESTIMATE_ITEM], "narrative": self.ESTIMATE_NARRATIVE,
            "title": self.ESTIMATE_TITLE, "sceneOneliner": self.ESTIMATE_SCENE,
        }
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "_run.py"), "show_app", json.dumps(request, ensure_ascii=False)],
            capture_output=True,
            text=True,
            env={**os.environ, **self.env_overrides},
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        lines = [line for line in completed.stdout.split("\n") if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("__ONEAGENT_APP_RESULT__"))
        self.assertFalse(json.loads(lines[0])["saved"])

    def test_future_clock_clamps_to_now(self) -> None:
        """模型把封面写成今晚 19:30 时，应收成上传时刻。"""
        now = store_now()
        future = now.replace(year=now.year + 1, hour=19, minute=30, second=0, microsecond=0)
        when = resolve_eaten_at(future.isoformat())
        self.assertEqual(when.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"))
        self.assertEqual((when.hour, when.minute), (now.hour, now.minute))

    def test_future_user_time_falls_back_to_upload(self) -> None:
        now = store_now()
        future = now.replace(year=now.year + 1, hour=19, minute=30, second=0, microsecond=0)
        result = dispatch({
            "operation": "record_meal",
            "title": "英式全早餐晚餐",
            "sceneOneliner": "模型乱猜的今晚七点。",
            "eatenAt": future.isoformat(),
            "eatenAtSource": "user",
            "aiPrice": 48,
            "items": [self.ESTIMATE_ITEM],
        })
        meal = result["current_meal"]
        self.assertEqual(meal["eaten_at_source"], "upload")
        self.assertTrue(meal["eaten_at"].startswith(now.strftime("%Y-%m-%d")))
        self.assertEqual(meal["ai_price"], 48)
        self.assertEqual(meal["ai_price_display"], "¥48")

    def test_missing_ai_price_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "aiPrice"):
            validate("record_meal", {
                "operation": "record_meal",
                "title": "午餐",
                "sceneOneliner": "测试",
                "items": [self.ESTIMATE_ITEM],
            })


if __name__ == "__main__":
    unittest.main()
