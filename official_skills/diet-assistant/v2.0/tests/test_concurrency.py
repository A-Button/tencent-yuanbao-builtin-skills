#!/usr/bin/env python3
"""两个沙箱共享一个挂载卷时的并发语义。

平台现在还没有跨会话共享的可写卷，所以这里手工把那个拓扑搭出来：两个进程的
DIET_DATA_DIR 指同一个目录（共享卷），DIET_WORK_DIR 各自独立（各有一份本地索引）。
卷一挂上，这就是线上的真实形状。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import store  # noqa: E402
from diet_api import MODEL_VIEW_KEY, dispatch  # noqa: E402

DATE = "2026-09-05"
MEAL_ID_RE = re.compile(r"^m_\d{4}-\d{2}-\d{2}_[a-z_]+_[0-9a-f]{8}$")

# 两个沙箱各写一个进程。栅栏卡在「meal_id 已定、对象还没落」这一瞬间——顺序跑的话
# 后开工的那个扫描时已经能看到前一个的对象，会走合并分支，撞不上。只控制时机，
# 不改被测逻辑。append_meal 和 replace_meal 都报到，这样万一走了合并分支，
# 对面不会白等到超时，用例能直接断言出条数不对。
_WORKER = r'''
import json, sys, time
from pathlib import Path

scripts, name, sync, request = sys.argv[1:5]
sys.path.insert(0, scripts)
import store, diet_api

def rendezvous():
    sync_dir = Path(sync)
    sync_dir.mkdir(parents=True, exist_ok=True)
    (sync_dir / (name + ".ready")).write_text("1")
    peer = sync_dir / (("B" if name == "A" else "A") + ".ready")
    deadline = time.time() + 30
    while not peer.is_file():
        if time.time() > deadline:
            raise TimeoutError("peer never arrived: " + name)
        time.sleep(0.01)

for attr in ("append_meal", "replace_meal"):
    original = getattr(store, attr)
    def barriered(*args, _original=original, **kwargs):
        rendezvous()
        return _original(*args, **kwargs)
    setattr(store, attr, barriered)

result = diet_api.dispatch(json.loads(request))
store.publish()
print(json.dumps(result[diet_api.MODEL_VIEW_KEY], ensure_ascii=False))
'''


def _record_request(title: str, iso: str, kcal: int = 300, emoji: str = "🍚") -> dict:
    return {
        "operation": "record_meal", "title": title, "sceneOneliner": f"{title}。",
        "eatenAt": iso, "aiPrice": 18,
        "items": [{"name": title, "portion": "一份", "emoji": emoji, "origin": "中国",
                   "kcal": kcal, "protein_g": 10, "fat_g": 5, "carb_g": 40, "sodium_mg": 200}],
    }


class SharedVolumeConcurrencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.shared = base / "shared-volume"   # 两个沙箱共用
        self.sync = base / "sync"              # 栅栏，不属于被测系统
        self.env_overrides = {
            "DIET_DATA_DIR": str(self.shared),
            "DIET_WORK_DIR": str(base / "work-main"),
        }
        self.previous_env = {k: os.environ.get(k) for k in self.env_overrides}
        os.environ.update(self.env_overrides)
        # store 用模块级变量记「本进程已经跟卷对过账」，用例之间要清掉，
        # 否则后一个用例读的是前一个临时目录留下的判断。
        store._scanned = False
        store._index_dirty = False

    def tearDown(self) -> None:
        for key, previous in self.previous_env.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        store._scanned = False
        store._index_dirty = False
        self.temp_dir.cleanup()

    # ---- 工具 ----

    def _sandbox(self, name: str, request: dict) -> subprocess.Popen:
        """起一个沙箱进程：共享卷同一个，本地索引各自一份。"""
        return subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(SCRIPTS), name, str(self.sync),
             json.dumps(request, ensure_ascii=False)],
            env={**os.environ,
                 "DIET_DATA_DIR": str(self.shared),
                 "DIET_WORK_DIR": str(Path(self.temp_dir.name) / f"work-{name}")},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def _run_two_sandboxes(self, request_a: dict, request_b: dict) -> list[dict]:
        procs = [self._sandbox("A", request_a), self._sandbox("B", request_b)]
        receipts = []
        for proc in procs:
            out, err = proc.communicate(timeout=90)
            self.assertEqual(proc.returncode, 0, f"沙箱进程失败：{err}")
            receipts.append(json.loads(out.strip().splitlines()[-1]))
        return receipts

    def _read_back(self) -> list[dict]:
        """拿一个干净的 work_dir 读共享卷，模拟事后另开一个会话来看。"""
        work = Path(self.temp_dir.name) / "work-reader"
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "diet_api.py"),
             json.dumps({"operation": "get_day", "date": DATE}, ensure_ascii=False)],
            capture_output=True, text=True, check=True,
            env={**os.environ, "DIET_DATA_DIR": str(self.shared), "DIET_WORK_DIR": str(work)},
        )
        return json.loads(completed.stdout)[MODEL_VIEW_KEY]["meals"]

    # ---- 并发 ----

    def test_two_sandboxes_same_day_same_type_keep_both_meals(self) -> None:
        """两个沙箱同天同餐次各记一餐，两条都得在。

        id 靠本地索引推序号的时候，两边都算出 ..._001、写同一个 key，
        后写的静默盖掉先写的——两顿不同的餐丢一顿，还不报错。
        """
        receipts = self._run_two_sandboxes(
            _record_request("沙箱A的番茄炒蛋盖饭", f"{DATE}T12:10:00+08:00", kcal=620, emoji="🍅"),
            _record_request("沙箱B的兰州拉面", f"{DATE}T12:40:00+08:00", kcal=540, emoji="🍜"),
        )
        ids = [r["meal_id"] for r in receipts]
        self.assertEqual(len(set(ids)), 2, f"两个沙箱算出了同一个 meal_id：{ids}")

        objects = sorted(p.stem for p in (self.shared / "meals").glob("*.json"))
        self.assertEqual(objects, sorted(ids), "挂载卷上的对象跟回执对不上")

        meals = self._read_back()
        self.assertEqual({m["title"] for m in meals},
                         {"沙箱A的番茄炒蛋盖饭", "沙箱B的兰州拉面"})
        self.assertEqual({round(m["kcal"]) for m in meals}, {620, 540},
                         "内容也要对，不能只是条数凑上")

    def test_same_slot_across_sandboxes_stays_independent(self) -> None:
        """两个沙箱同记午餐：本来就该是两条独立卡，再补记也是第三条，不合并。"""
        self._run_two_sandboxes(
            _record_request("沙箱A的午餐", f"{DATE}T12:10:00+08:00", kcal=620),
            _record_request("沙箱B的午餐", f"{DATE}T12:40:00+08:00", kcal=540),
        )
        self.assertEqual(len(self._read_back()), 2)
        third = dispatch(_record_request("补记一份汤", f"{DATE}T13:00:00+08:00", kcal=100))
        self.assertNotIn("merged", third[MODEL_VIEW_KEY])
        self.assertEqual(len(self._read_back()), 3, "同槽补记应新增第三条独立卡")

    # ---- 单沙箱：原有语义不变 ----

    def test_single_sandbox_consecutive_meals_get_distinct_ids(self) -> None:
        """一个沙箱连着记不同餐次/不同天，id 不能重复。"""
        ids = [
            dispatch(_record_request("早餐", f"{DATE}T08:00:00+08:00"))[MODEL_VIEW_KEY]["meal_id"],
            dispatch(_record_request("午餐", f"{DATE}T12:00:00+08:00"))[MODEL_VIEW_KEY]["meal_id"],
            dispatch(_record_request("晚餐", f"{DATE}T18:00:00+08:00"))[MODEL_VIEW_KEY]["meal_id"],
            dispatch(_record_request("次日午餐", "2026-09-06T12:00:00+08:00"))[MODEL_VIEW_KEY]["meal_id"],
        ]
        self.assertEqual(len(set(ids)), 4, f"id 撞了：{ids}")
        for meal_id in ids:
            with self.subTest(meal_id=meal_id):
                self.assertRegex(meal_id, MEAL_ID_RE)

    def test_generated_ids_carry_enough_entropy(self) -> None:
        """后缀得是随机的，不能退回序号。

        真正的回归防线是格式断言：序号化的实现过不了 8 位十六进制这一关。
        条数只当个廉价的抽样，别往上加——随机 id 本来就有生日界，200 抽的
        碰撞概率是 5e-6，加到 2000 就变成 11%，那是把用例改成抛硬币。
        """
        drawn = {store.new_meal_id(DATE, "lunch") for _ in range(200)}
        self.assertEqual(len(drawn), 200)
        for meal_id in drawn:
            self.assertRegex(meal_id, MEAL_ID_RE)

    def test_same_slot_within_one_sandbox_makes_two_cards(self) -> None:
        """索引正常时：同槽再记一次是新建，两条对象、两个 meal_id、热量各算各的。"""
        first = dispatch(_record_request("早餐一", f"{DATE}T07:00:00+08:00", kcal=300))
        first_id = first[MODEL_VIEW_KEY]["meal_id"]

        second = dispatch(_record_request("早餐二", f"{DATE}T09:00:00+08:00", kcal=100))
        self.assertNotEqual(second[MODEL_VIEW_KEY]["meal_id"], first_id)
        self.assertNotIn("merged", second[MODEL_VIEW_KEY])

        meal = second["current_meal"]
        self.assertEqual(meal["title"], "早餐二")
        self.assertEqual(meal["eaten_at"], f"{DATE}T09:00:00+08:00")
        self.assertEqual(round(meal["totals"]["kcal"]), 100)
        self.assertEqual(len([p for p in (self.shared / "meals").glob("*.json")]), 2,
                         "同槽多卡应落两个对象文件")
        self.assertEqual(len(self._read_back()), 2)

if __name__ == "__main__":
    unittest.main()
