#!/usr/bin/env python3
"""出发前按已知班次复查同程静态时刻；不声称有个人座次或实时口号。"""

from __future__ import annotations

import datetime as dt
import json
import sys

sys.dont_write_bytecode = True

import provider_api
from tongcheng_fill import lookup_ticket


def _value(args: dict, key: str) -> str:
    value = args.get(key)
    return value.strip() if isinstance(value, str) else ""


def check_ticket(args: dict) -> dict:
    kind = _value(args, "kind")
    no = _value(args, "no")
    date = _value(args, "date")
    dep_city = _value(args, "depCity")
    arr_city = _value(args, "arrCity")
    dep_station = _value(args, "depStation")
    if kind not in ("flight", "train"):
        return {"ok": False, "code": "INVALID_KIND", "message": "kind 只能是 flight 或 train"}
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        return {"ok": False, "code": "INVALID_DATE", "message": "date 必须是 YYYY-MM-DD"}
    if not all((no, dep_city, arr_city)) or (kind == "train" and not dep_station):
        return {"ok": False, "code": "MISSING_IDENTITY", "message": "须给班次、日期、出发到达城市；火车还须给用户上车站"}
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        found = lookup_ticket(kind, no, date, dep_city, arr_city, dep_station=dep_station)
    except provider_api.ProviderError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message, "checkedAt": checked_at}
    if not found:
        return {"ok": False, "code": "NOT_FOUND", "message": "没有查到与班次、日期及出发站匹配的记录", "checkedAt": checked_at}
    if found.get("_alts"):
        return {"ok": False, "code": "AMBIGUOUS", "message": "同一班次存在多个出发记录，请核实出发机场或车站", "checkedAt": checked_at}
    ticket = {key: found.get(key, "") for key in
              ("kind", "no", "depTime", "depPlace", "arrTime", "arrPlace")}
    ticket.update(date=date, depCity=dep_city, arrCity=arr_city)
    if not ticket["depTime"] or not ticket["depPlace"]:
        return {"ok": False, "code": "INCOMPLETE", "message": "该班次缺少出发时刻或出发站", "checkedAt": checked_at}
    return {
        "ok": True,
        "source": "同程静态班次",
        "checkedAt": checked_at,
        "ticket": ticket,
        "unavailable": ["个人车厢座位", "检票口", "站台", "登机口", "实时运行状态"],
    }


def main() -> int:
    try:
        args = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    except json.JSONDecodeError:
        args = None
    result = check_ticket(args) if isinstance(args, dict) else {
        "ok": False, "code": "INVALID_INPUT", "message": "入参必须是 JSON 对象"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
