#!/usr/bin/env python3
"""Adhoc 脚本模板 — cp 到 /workspace/.scripts/{slug}.py 后填空使用.

⚠ 写前必先 read custom-script-guide.md 获取黄金规则!

使用场景:
    用户问题触发第二级 Autonomous Mode. 本脚本沿着:
        read custom-script-guide.md
     -> cp 本模板到 /workspace/.scripts/{slug}.py
     -> 填入业务逻辑
     -> bash python /workspace/.scripts/{slug}.py [args]

数据源边界:
    - 申万官网(swsresearch.com)数据: 统一从 sw_common 取 (禁止直连官网 HTTP)
    - 港美股/大宗商品/宏观等跨市场数据: 不受限制, 可通过 WorkBuddy 能力获取:
        * 路由到已安装 skill (stock-query / neodata-financial-search / 用户自定义 skill)
        * WebSearch / 已连接的金融 Connector
        * 或在脚本内 subprocess 调用其他 skill 的取数脚本
      第三方数据需在输出中标注来源与数据时点/口径.

Slug 命名建议 (语义化, 不用 tmp.py):
    sector_rotation_2026.py
    consecutive_pe_decline_tmt.py
    bank_3yr_rolling_sharpe.py
    us_sector_vs_sw_industry_linkage.py

追问处理:
    - 参数变 -> 不改代码, 重跑 python .scripts/{slug}.py --new-args
    - 逻辑变 -> Edit 本文件改代码, slug 保持不变
    - 方向变 -> 新建一个新 slug 的脚本
"""

from __future__ import annotations

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
# 若脚本位于 workspace/.scripts/, 把本 skill 的 scripts/ 也加入路径以便 import sw_common:
SKILL_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if os.path.isdir(SKILL_SCRIPTS) and SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)
import traceback

# ─── 申万官网数据: 从 sw_common 函数库取 (禁止直接 HTTP 打官网) ────────
# 按需选择需要的函数, 不需要的删掉:
#
# from sw_common import fetch_kline_one          # 单指数 K 线
# from sw_common import fetch_realtime_one       # 单指数实时行情
# from sw_common import fetch_component_stocks   # 成分股
# from sw_common import fetch_period_snapshot    # 月末截面快照
# from sw_common import fetch_risk_return_one    # 收益风险
# from sw_common import fetch_fundamentals_batch # 基本面(PE/PB/股息率等)
# from sw_common import INDUSTRY_L1, STYLE_INDICES, MARKET_INDICES  # 代码表
#
# ★ 更多函数见 scripts/sw_common.py 源码

# ─── 跨市场/第三方数据 (可选, WorkBuddy 平台能力) ────────────────────────
# 方式 1: subprocess 调其他已安装 skill 的脚本取数 (如 stock-query 行情脚本)
#   import subprocess
#   r = subprocess.run(["python", "<stock-query skill 路径>/scripts/xxx.py", "--arg", "v"],
#                      capture_output=True, text=True, encoding="utf-8")
#   data = json.loads(r.stdout.strip().split("\n")[-1])
#
# 方式 2: 脚本内调用已连接的金融 Connector / 外部公开 API (标注来源)
#   from datasource import get_kline, get_quote  # 仅通过已授权 westock CLI 取数
#   ... # 获取后把来源写进 summary_text
#
# 方式 3: 官网数据 + 第三方数据混合分析时, 分源取数后合并计算,
#         并在 summary_text / 数据说明中分别标注来源与时点/口径.

# ─── 也可以 subprocess 调本 skill 预设脚本 (方式 B, UI 推送) ────────────
# import subprocess
# r = subprocess.run([
#     "python",
#     os.path.join(SKILL_SCRIPTS, "sw_XXX.py"),
#     "--arg", "value"
# ], capture_output=True, text=True, encoding="utf-8")
# summary = json.loads(r.stdout.strip().split("\n")[-1])


# ═══════════════════════════════════════════════════════════════════════
#  ★ 在此填写业务逻辑 ★
# ═══════════════════════════════════════════════════════════════════════

def compute(args) -> dict:
    """核心业务逻辑. 返回 dict, 会被 main() 序列化成 stdout JSON.

    Returns:
        dict 必须含 status 和 summary_text:
        {
            "status": "ok",
            "summary_text": "自然语言摘要, agent 回复时引用",
            ...其他数据...
        }
        跨市场/第三方数据需在 summary_text 或单独字段标注来源与时点.
    """
    # 示例: 拉一个指数的 K 线算年化收益率
    #
    # from sw_common import fetch_kline_one
    # kline = fetch_kline_one(args.code, period="DAY", days=args.days)
    # # ...业务计算...
    # annual_return = ...
    # return {
    #     "status": "ok",
    #     "summary_text": f"{args.name}({args.code}) 近 {args.days} 日年化 {annual_return:.2f}%",
    #     "annual_return": annual_return,
    # }

    raise NotImplementedError("Fill in compute() with your business logic")


# ═══════════════════════════════════════════════════════════════════════
#  以下框架代码通常不用改
# ═══════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="{一句话描述你的脚本做什么}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ─── 常用参数槽 (根据实际需要增删) ──────────────────────────
    # 推荐尽量多暴露参数 (--help 里能看到), 追问改参数不用改代码.

    parser.add_argument("--code", default=None, help="指数代码, 如 801780")
    parser.add_argument("--name", default=None, help="指数名称, 如 银行 (显示用)")
    parser.add_argument("--scope", default="all",
                        help="板块范围: all / consumer / tmt / cyclical / finance / mfg / defensive")
    parser.add_argument("--days", type=int, default=250, help="回溯交易日数")
    parser.add_argument("--start", default=None, help="起始日期 YYYYMMDD (与 --days 互斥)")
    parser.add_argument("--end", default=None, help="结束日期 YYYYMMDD")
    parser.add_argument("--verbose", action="store_true", help="输出中间过程调试信息")

    return parser.parse_args()


def main():
    args = parse_args()

    try:
        result = compute(args)

        # 校验返回格式
        if not isinstance(result, dict):
            raise TypeError(f"compute() must return dict, got {type(result).__name__}")
        if "status" not in result:
            result["status"] = "ok"
        if "summary_text" not in result:
            raise ValueError("compute() return dict must contain 'summary_text'")

        # stdout 最后一行: JSON 摘要 (agent 读这行生成回复)
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        err = {
            "status": "error",
            "message": str(e),
            "type": type(e).__name__,
        }
        if args.verbose:
            err["traceback"] = traceback.format_exc()
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
