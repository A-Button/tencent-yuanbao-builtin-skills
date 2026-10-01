#!/usr/bin/env python3
"""Compute reminder intents only; never create host objects or send notifications."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def plan(payload: dict, now: datetime | None = None) -> dict:
    zone = ZoneInfo(payload.get("timezone", "Asia/Shanghai"))
    now = now or datetime.now(zone)
    if now.tzinfo is None:
        raise ValueError("now 必须包含时区")
    now = now.astimezone(zone)
    if payload.get("authorized") is not True:
        raise ValueError("需要用户明确提醒授权；本脚本不代替授权判断")
    visits, seen = [], set()
    for visit in payload.get("visits", []):
        visit_id = visit.get("visit_id")
        if not isinstance(visit_id, str) or not visit_id.strip() or visit_id in seen:
            raise ValueError("每次就诊需要唯一非空 visit_id")
        seen.add(visit_id)
        if visit.get("date_confirmed") is not True or visit.get("date_source") not in ("user_selected", "doctor_arrangement", "confirmed_booking"):
            raise ValueError("只有参考日期或用户未确认时，不生成提醒计划")
        if visit.get("appointment_status") not in ("booked", "not_booked", "unknown"):
            raise ValueError("需要明确预约状态，未知可写 unknown，不推定已预约")
        raw = datetime.fromisoformat(visit["date"] + "T00:00:00")
        action_date = raw.date()
        specs = visit.get("reminders", [{"purpose": "booking", "days_before": 7, "time": "08:00"}, {"purpose": "vaccination", "days_before": 0, "time": "08:00"}])
        reminders, skipped, unique = [], [], set()
        if not isinstance(specs, list) or not specs:
            raise ValueError("提醒列表不能为空；取消由宿主管理，不生成空计划")
        for spec in specs:
            purpose, days = spec.get("purpose"), spec.get("days_before")
            if purpose not in ("booking", "vaccination") or type(days) is not int or days < 0:
                raise ValueError("提醒目的／提前天数无效")
            at_time = time.fromisoformat(spec["time"])
            if at_time.tzinfo is not None:
                raise ValueError("time 不带时区；使用顶层 timezone")
            at = datetime.combine(action_date - timedelta(days=days), at_time, zone)
            identity = (purpose, at.isoformat())
            if identity in unique:
                raise ValueError("同一就诊存在重复提醒")
            unique.add(identity)
            item = {"purpose": purpose, "at": at.isoformat(), "days_before": days}
            if purpose == "booking" and visit["appointment_status"] == "booked":
                skipped.append({**item, "reason": "already_booked"})
            elif at <= now:
                skipped.append({**item, "reason": "time_elapsed"})
            else:
                reminders.append({**item, "callback": callback(purpose)})
        visits.append({"visit_id": visit_id, "action_date": action_date.isoformat(), "date_source": visit["date_source"],
                       "appointment_status": visit["appointment_status"], "reminders": reminders, "skipped": skipped})
    if not visits:
        raise ValueError("缺少就诊计划")
    return {"status": "planned_not_created", "timezone": str(zone), "calculated_at": now.isoformat(), "visits": visits,
            "expected_reminder_count": sum(len(v["reminders"]) for v in visits),
            "skipped_count": sum(len(v["skipped"]) for v in visits)}


def callback(purpose: str) -> str:
    condition = "若已预约，不再发送预约提醒。" if purpose == "booking" else "若已确认本次接种完成，不再发送接种提醒。"
    return ("先加载 yuanbao-vaccine-reminder 的 SKILL.md 和 references/host.md，再加载 make-things 及其 show_widget Schema；"
            "以可信回调关联读取最新 Thing/Todo，核对绑定、行动日期、状态和本次提醒回执。"
            "已取消、暂停、改期、已完成或本事件已发布时，不执行旧提醒。" + condition +
            "仍需提醒时按疫苗 Skill 固定格式调用 show_widget：显式 card_type=image_text、data={}；标题按称呼、绝对日期、完整疫苗剂次紧凑排列；单疫苗目标28字符，多疫苗优先列全，28字不是硬上限；"
            "summary 只放机构及必要院区，删除街道门牌，目标20字符；按主Skill预算计数压缩但不机械截断或删关键事实，缺失字段省略；无图片和 actions，不用 todo_remind 或 recommend_list；卡面日期仅月日（跨年带年份），不写星期、上午下午或具体时段；已确认时段保留在会话详情及原安排中，不修改 Todo／Trigger 时间。"
            "调用前核对以上实际参数及真实事项关联，保留日期来源，计划不写成已预约。"
            "按宿主真实回包记录发布结果，成功后收口本次一次性提醒；未知先查询，不盲目重发。"
            "不要因通知已发将接种 Todo 标为 DONE；只有实际接种事实确认后才完成相应行动。"
            "show_widget 不可用时如实报告卡片未发布；卡片发布不等于系统推送送达。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(plan(json.loads(args.input.read_text(encoding="utf-8"))), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
