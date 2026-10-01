#!/usr/bin/env python3
"""commit_checkin 契约 + 落库回归：主动确认 / 超时自动确认。"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from cli_contract import ContractError, audit_operation_specs, validate_operation  # noqa: E402
import ledger_api  # noqa: E402


def _ok(name: str) -> None:
    print(f"  PASS  {name}")


def _fail(name: str, detail: str) -> None:
    print(f"  FAIL  {name}: {detail}")
    raise AssertionError(f"{name}: {detail}")


def _card_id() -> str:
    return f"test_{uuid.uuid4().hex[:10]}"


_TODAY = "2026-09-30"
_dist_seq = 0


def _dist(base: float = 6.0) -> float:
    global _dist_seq
    _dist_seq += 1
    return round(base + _dist_seq * 0.01, 2)


def _base_commit(**overrides) -> dict:
    args = {
        "member": "杨老师",
        "occurred_at": _TODAY,
        "activity_type": "outdoor_run",
        "distance_raw": _dist(),
        "unit": "km",
        "today": _TODAY,
        "card_id": _card_id(),
    }
    args.update(overrides)
    return args


# ---------------------------------------------------------------------------
# 契约层
# ---------------------------------------------------------------------------

def test_spec_audit() -> None:
    issues = audit_operation_specs()
    if issues:
        _fail("audit_operation_specs", "; ".join(issues))
    _ok("audit_operation_specs")


def test_contract_with_duration() -> None:
    args = _base_commit(duration_seconds=4040)
    out = validate_operation("commit_checkin", args, agent_call=True)
    if out.get("duration_seconds") != 4040:
        _fail("contract_with_duration", f"got {out}")
    _ok("contract_with_duration")


def test_contract_without_duration() -> None:
    args = _base_commit()
    validate_operation("commit_checkin", args, agent_call=True)
    _ok("contract_without_duration")


def test_contract_rejects_unknown() -> None:
    args = _base_commit(duration_seconds=1800, foo_bar=1)
    try:
        validate_operation("commit_checkin", args, agent_call=True)
        _fail("contract_rejects_unknown", "应拒绝未知字段")
    except ContractError as exc:
        if "foo_bar" not in str(exc):
            _fail("contract_rejects_unknown", str(exc))
    _ok("contract_rejects_unknown")


# ---------------------------------------------------------------------------
# 集成：主动确认（用户点确认）
# ---------------------------------------------------------------------------

def test_manual_commit_with_duration() -> None:
    """普通成员 + duration_seconds（王阳日志同款参数形态）。"""
    args = _base_commit(
        member="杨老师",
        activity_type="treadmill",
        distance_raw=13.46,
        duration_seconds=4040,
    )
    r = ledger_api.execute("commit_checkin", args, agent_call=True)
    if r.get("status") != "confirmed":
        _fail("manual_commit_with_duration", json.dumps(r, ensure_ascii=False)[:500])
    if not r.get("receipt", {}).get("event_id"):
        _fail("manual_commit_with_duration", "无 event_id")
    _ok("manual_commit_with_duration")


def test_manual_commit_age_exempt_no_duration() -> None:
    args = _base_commit(
        member="陈成辉",
        distance_raw=_dist(6.5),
    )
    r = ledger_api.execute("commit_checkin", args, agent_call=True)
    if r.get("status") != "confirmed":
        _fail("manual_commit_age_exempt_no_duration", json.dumps(r, ensure_ascii=False)[:500])
    _ok("manual_commit_age_exempt_no_duration")


def test_manual_commit_fail_reissues_card() -> None:
    """非豁免缺 duration → 落库失败 → 主动确认应 cancel 旧卡 + 出新 pending 卡。"""
    old_id = _card_id()
    args = _base_commit(member="杨老师", card_id=old_id)
    r = ledger_api.execute("commit_checkin", args, agent_call=True)
    if r.get("phase") != "error":
        _fail("manual_fail_reissue", f"期望 phase=error，got {r.get('phase')}")
    if not r.get("reissued"):
        _fail("manual_fail_reissue", "期望 reissued=true")
    if r.get("cancelled_card_id") != old_id:
        _fail("manual_fail_reissue", f"cancelled_card_id={r.get('cancelled_card_id')}")
    if not r.get("new_card_id"):
        _fail("manual_fail_reissue", "缺少 new_card_id")
    cards = r.get("cards") or []
    if len(cards) < 2:
        _fail("manual_fail_reissue", f"cards 数量={len(cards)}")
    if cards[0].get("status") != "cancelled":
        _fail("manual_fail_reissue", "第一张卡应为 cancelled")
    if cards[1].get("status") != "pending":
        _fail("manual_fail_reissue", "第二张卡应为 pending")
    _ok("manual_fail_reissue")


# ---------------------------------------------------------------------------
# 集成：自动确认（超时 auto=true）
# ---------------------------------------------------------------------------

def test_auto_commit_with_duration() -> None:
    args = _base_commit(member="杨老师", duration_seconds=3600, auto=True)
    r = ledger_api.execute("commit_checkin", args, agent_call=True)
    if r.get("status") != "confirmed":
        _fail("auto_commit_with_duration", json.dumps(r, ensure_ascii=False)[:500])
    _ok("auto_commit_with_duration")


def test_auto_commit_age_exempt_no_duration() -> None:
    args = _base_commit(member="陈成辉", distance_raw=_dist(7.0), auto=True)
    r = ledger_api.execute("commit_checkin", args, agent_call=True)
    if r.get("status") != "confirmed":
        _fail("auto_commit_age_exempt_no_duration", json.dumps(r, ensure_ascii=False)[:500])
    _ok("auto_commit_age_exempt_no_duration")


def test_auto_commit_fail_cancel_only() -> None:
    """auto=true 失败：只 cancel，不出新卡。"""
    old_id = _card_id()
    args = _base_commit(member="杨老师", card_id=old_id, auto=True)
    r = ledger_api.execute("commit_checkin", args, agent_call=True)
    if r.get("phase") != "error":
        _fail("auto_fail_cancel_only", f"phase={r.get('phase')}")
    if r.get("reissued"):
        _fail("auto_fail_cancel_only", "auto 失败不应 reissued")
    if r.get("new_card_id"):
        _fail("auto_fail_cancel_only", "auto 失败不应 new_card_id")
    if r.get("cancelled_card_id") != old_id:
        _fail("auto_fail_cancel_only", f"cancelled_card_id={r.get('cancelled_card_id')}")
    cards = r.get("cards") or []
    if len(cards) != 1 or cards[0].get("status") != "cancelled":
        _fail("auto_fail_cancel_only", f"cards={cards}")
    _ok("auto_fail_cancel_only")


# ---------------------------------------------------------------------------
# draft → commit 端到端（主动确认完整链路）
# ---------------------------------------------------------------------------

def test_draft_then_manual_commit() -> None:
    cid = _card_id()
    draft_args = {
        "user_id": "user_1",
        "member": "杨老师",
        "occurred_at": _TODAY,
        "activity_type": "outdoor_run",
        "distance_raw": _dist(8.0),
        "unit": "km",
        "duration_seconds": 2880,
        "today": _TODAY,
        "card_id": cid,
    }
    draft = ledger_api.execute("draft_checkin", draft_args, agent_call=True)
    if draft.get("status") != "pending":
        _fail("draft_then_commit", f"draft status={draft.get('status')}")
    commit_args = {
        "member": draft_args["member"],
        "occurred_at": draft_args["occurred_at"],
        "activity_type": draft_args["activity_type"],
        "distance_raw": draft_args["distance_raw"],
        "unit": draft_args["unit"],
        "duration_seconds": draft_args["duration_seconds"],
        "today": draft_args["today"],
        "card_id": draft.get("card_id") or cid,
    }
    commit = ledger_api.execute("commit_checkin", commit_args, agent_call=True)
    if commit.get("status") != "confirmed":
        _fail("draft_then_commit", json.dumps(commit, ensure_ascii=False)[:500])
    _ok("draft_then_commit")


def main() -> int:
    tests = [
        test_spec_audit,
        test_contract_with_duration,
        test_contract_without_duration,
        test_contract_rejects_unknown,
        test_manual_commit_with_duration,
        test_manual_commit_age_exempt_no_duration,
        test_manual_commit_fail_reissues_card,
        test_auto_commit_with_duration,
        test_auto_commit_age_exempt_no_duration,
        test_auto_commit_fail_cancel_only,
        test_draft_then_manual_commit,
    ]
    print(f"running {len(tests)} tests …")
    failed = 0
    for fn in tests:
        name = fn.__name__
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
            traceback.print_exc()
    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILED'} ({len(tests) - failed}/{len(tests)})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
