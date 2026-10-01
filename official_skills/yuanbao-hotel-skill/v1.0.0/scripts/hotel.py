#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RollingGo 酒店连接器 API 调用工具 (免第三方依赖，纯 Python 3 标准库)
供 Agent 在具备代码执行/沙箱环境时直接调用
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_BASE_URL = os.environ.get("MCP_BASE_URL", "https://mcp.rollinggo.cn/mcp")

def get_default_token():
    return os.environ.get("ACCESS_TOKEN") or os.environ.get("TOKEN") or os.environ.get("MCP_TOKEN") or ""

def request_api(endpoint, method="POST", payload=None, token=None, base_url=None):
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    url = f"{base}/{endpoint.lstrip('/')}"
    req_token = token or get_default_token()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "RollingGo-Agent-Skill/1.0"
    }
    if req_token:
        headers["Authorization"] = f"Bearer {req_token}"

    data_bytes = None
    if payload is not None and method.upper() == "POST":
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except Exception:
            return {"success": False, "code": e.code, "message": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"success": False, "code": 5000, "message": str(e)}

def cmd_tags(args):
    res = request_api("hoteltags", method="GET", token=args.token, base_url=args.base_url)
    print(json.dumps(res, ensure_ascii=False, indent=2))

def cmd_search(args):
    payload = {
        "originQuery": args.origin_query,
        "place": args.place,
        "placeType": args.place_type,
        "size": args.size,
    }
    check_in = {}
    if args.check_in_date:
        check_in["checkInDate"] = args.check_in_date
    if args.stay_nights is not None:
        check_in["stayNights"] = args.stay_nights
    if args.adult_count is not None:
        check_in["adultCount"] = args.adult_count
    if check_in:
        payload["checkInParam"] = check_in

    filter_opts = {}
    if args.star_ratings:
        parts = [float(x.strip()) for x in args.star_ratings.split(",")]
        filter_opts["starRatings"] = parts
    dist = args.distance_in_meter if args.distance_in_meter is not None else args.distance
    if dist is not None:
        filter_opts["distanceInMeter"] = dist
    if filter_opts:
        payload["filterOptions"] = filter_opts

    tags = {}
    req_tags = args.required_tags or args.required_tag
    if req_tags:
        tags["requiredTags"] = [t.strip() for t in req_tags.split(",") if t.strip()]
    pref_brands = args.preferred_brands or args.preferred_brand
    if pref_brands:
        tags["preferredBrands"] = [b.strip() for b in pref_brands.split(",") if b.strip()]
    max_price = args.max_price_per_night if args.max_price_per_night is not None else args.max_price
    if max_price is not None:
        tags["maxPricePerNight"] = max_price
    if tags:
        payload["hotelTags"] = tags

    res = request_api("hotelsearch", method="POST", payload=payload, token=args.token, base_url=args.base_url)
    print(json.dumps(res, ensure_ascii=False, indent=2))

def cmd_detail(args):
    if not args.hotel_id and not args.name:
        print(json.dumps({"success": False, "code": 4001, "message": "参数错误: 必须提供 --hotel-id 或 --name"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    payload = {}
    if args.hotel_id:
        payload["hotelId"] = args.hotel_id
    if args.name:
        payload["name"] = args.name

    if args.check_in_date or args.check_out_date:
        payload["dateParam"] = {
            "checkInDate": args.check_in_date,
            "checkOutDate": args.check_out_date
        }

    occupancy = {
        "roomCount": args.room_count,
        "adultCount": args.adult_count,
        "childCount": args.child_count
    }
    child_ages = args.child_ages or args.child_age
    if child_ages:
        occupancy["childAgeDetails"] = [int(x.strip()) for x in child_ages.split(",") if x.strip()]
    payload["occupancyParam"] = occupancy

    filter_obj = {}
    if args.cancel_policy:
        filter_obj["cancelPolicy"] = args.cancel_policy
    if args.meal_type:
        filter_obj["mealType"] = args.meal_type
    if filter_obj:
        payload["filter"] = filter_obj

    res = request_api("hoteldetail", method="POST", payload=payload, token=args.token, base_url=args.base_url)
    print(json.dumps(res, ensure_ascii=False, indent=2))

def cmd_price_confirm(args):
    rooms = args.rooms if args.rooms is not None else (args.room_count or 1)
    adults = args.adults if args.adults is not None else (args.adult_count or 2)
    children = args.children if args.children is not None else (args.child_count or 0)
    child_ages_str = args.child_ages or args.child_age
    child_ages = [int(x.strip()) for x in child_ages_str.split(",") if x.strip()] if child_ages_str else None

    occupancy_details = []
    for r in range(1, rooms + 1):
        item = {
            "roomNum": r,
            "adultCount": adults,
            "childCount": children
        }
        if child_ages:
            item["childAgeDetails"] = child_ages
        occupancy_details.append(item)

    payload = {
        "hotelID": args.hotel_id,
        "ratePlanID": args.rate_plan_id,
        "numOfRooms": rooms,
        "dateParam": {
            "checkInDate": args.check_in_date,
            "checkOutDate": args.check_out_date
        },
        "occupancyDetails": occupancy_details
    }
    res = request_api("hotelpriceconfirm", method="POST", payload=payload, token=args.token, base_url=args.base_url)
    print(json.dumps(res, ensure_ascii=False, indent=2))

def cmd_book(args):
    raw_guests = args.guests or args.guest
    guest_list = []
    
    if raw_guests:
        # 格式: 房间号,名字,姓氏,是否成人[,年龄] (多个分号分隔，如: "1,SAN,ZHANG,true;1,SI,LI,true;1,XIAO,ZHANG,false,6")
        for entry in raw_guests.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            parts = [p.strip() for p in entry.split(",")]
            room_num = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 1
            first_name = parts[1] if len(parts) > 1 else (args.first_name or "")
            last_name = parts[2] if len(parts) > 2 else (args.last_name or "")
            is_adult = parts[3].lower() != "false" if len(parts) > 3 else True
            age = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None
            
            room_entry = next((r for r in guest_list if r["roomNum"] == room_num), None)
            if not room_entry:
                room_entry = {"roomNum": room_num, "guestInfo": []}
                guest_list.append(room_entry)
            
            g_info = {
                "firstName": first_name,
                "lastName": last_name,
                "isAdult": is_adult
            }
            if age is not None:
                g_info["age"] = age
            room_entry["guestInfo"].append(g_info)
    else:
        fn = args.first_name or "SAN"
        ln = args.last_name or "ZHANG"
        guest_list = [{
            "roomNum": 1,
            "guestInfo": [{
                "firstName": fn,
                "lastName": ln,
                "isAdult": True
            }]
        }]

    # 联系人名与姓如果未显式提供，默认回退取首位客人
    contact_fn = args.first_name
    contact_ln = args.last_name
    if (not contact_fn or not contact_ln) and guest_list and guest_list[0]["guestInfo"]:
        first_g = guest_list[0]["guestInfo"][0]
        contact_fn = contact_fn or first_g["firstName"]
        contact_ln = contact_ln or first_g["lastName"]

    if not contact_fn or not contact_ln:
        print(json.dumps({"success": False, "code": 4001, "message": "参数错误: 必须提供联系人姓名 (--first-name / --last-name) 或客人信息"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    if not args.email:
        print(json.dumps({"success": False, "code": 4001, "message": "参数错误: 必须提供联系邮箱 (--email)"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    payload = {
        "referenceNo": args.reference_no,
        "contact": {
            "firstName": contact_fn,
            "lastName": contact_ln,
            "email": args.email
        },
        "guestList": guest_list
    }
    req_text = args.customer_request or args.request
    if req_text:
        payload["customerRequest"] = req_text

    res = request_api("hotelbook", method="POST", payload=payload, token=args.token, base_url=args.base_url)
    print(json.dumps(res, ensure_ascii=False, indent=2))

def cmd_orders(args):
    payload = {"status": args.status}
    if args.start_date and args.end_date:
        payload["dateRange"] = {
            "startDate": args.start_date,
            "endDate": args.end_date
        }
    res = request_api("hotelorders", method="POST", payload=payload, token=args.token, base_url=args.base_url)
    print(json.dumps(res, ensure_ascii=False, indent=2))

def cmd_order_detail(args):
    order_no = args.order_no or args.order_no_pos
    if not order_no:
        print(json.dumps({"success": False, "code": 4001, "message": "参数错误: 必须提供订单号 (--order-no)"}, ensure_ascii=False, indent=2))
        sys.exit(1)
    payload = {"orderNo": order_no}
    res = request_api("hotelorderdetail", method="POST", payload=payload, token=args.token, base_url=args.base_url)
    print(json.dumps(res, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser(description="RollingGo 酒店 API 命令行代理工具 (纯标准库，零外部依赖)")
    parser.add_argument("--token", "-t", help="Bearer Access Token（缺省时读取环境变量 ACCESS_TOKEN / TOKEN / MCP_TOKEN）")
    parser.add_argument("--base-url", help="API Base URL (缺省使用 MCP_BASE_URL 或 https://mcp.rollinggo.cn/mcp)")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 1. tags
    subparsers.add_parser("hotel-tags", help="获取可用搜索标签字典")

    # 2. search
    p_search = subparsers.add_parser("search-hotels", help="搜索酒店列表")
    p_search.add_argument("--origin-query", required=True, help="用户原始完整意图")
    p_search.add_argument("--place", required=True, help="地点名称（景点/车站/详细地址等必须包含城市前缀，如 杭州西湖）")
    p_search.add_argument("--place-type", required=True, choices=["城市", "机场", "景点", "火车站", "地铁站", "酒店", "区/县", "详细地址"], help="地点类型")
    p_search.add_argument("--size", type=int, default=5, help="返回数量 (默认5)")
    p_search.add_argument("--check-in-date", help="入住日期 YYYY-MM-DD")
    p_search.add_argument("--stay-nights", type=int, default=1, help="入住晚数 (默认1)")
    p_search.add_argument("--adult-count", type=int, default=2, help="每间房成人数 (默认2)")
    p_search.add_argument("--star-ratings", help="星级范围，如 4.0,5.0")
    p_search.add_argument("--distance-in-meter", type=int, help="距离限制（米）")
    p_search.add_argument("--distance", type=int, help="距离限制（米，同 --distance-in-meter）")
    p_search.add_argument("--required-tags", help="硬性标签，逗号分隔")
    p_search.add_argument("--required-tag", help="同 --required-tags")
    p_search.add_argument("--preferred-brands", help="偏好品牌，逗号分隔")
    p_search.add_argument("--preferred-brand", help="同 --preferred-brands")
    p_search.add_argument("--max-price-per-night", type=float, help="每晚最高预算")
    p_search.add_argument("--max-price", type=float, help="同 --max-price-per-night")

    # 3. detail
    p_detail = subparsers.add_parser("hotel-detail", help="查询酒店房型报价与政策")
    p_detail.add_argument("--hotel-id", type=int, help="酒店ID (与 --name 二选一)")
    p_detail.add_argument("--name", help="酒店名称模糊搜索 (与 --hotel-id 二选一)")
    p_detail.add_argument("--check-in-date", required=True, help="入住日期 YYYY-MM-DD")
    p_detail.add_argument("--check-out-date", required=True, help="离店日期 YYYY-MM-DD")
    p_detail.add_argument("--room-count", type=int, default=1, help="房间数 (默认1)")
    p_detail.add_argument("--adult-count", type=int, default=2, help="每间房成人数 (默认2)")
    p_detail.add_argument("--child-count", type=int, default=0, help="每间房儿童数 (默认0)")
    p_detail.add_argument("--child-ages", help="儿童年龄，逗号分隔，如 3,5")
    p_detail.add_argument("--child-age", help="同 --child-ages")
    p_detail.add_argument("--cancel-policy", choices=["CANCELABLE", "NON_CANCELABLE"], help="取消政策筛选")
    p_detail.add_argument("--meal-type", choices=["WITH_BREAKFAST", "SINGLE_BREAKFAST", "DOUBLE_BREAKFAST", "NO_MEAL"], help="餐食类型筛选")

    # 4. price confirm
    p_price = subparsers.add_parser("price-confirm", help="锁定实时房型价格并换取 referenceNo")
    p_price.add_argument("--hotel-id", type=int, required=True, help="酒店ID")
    p_price.add_argument("--rate-plan-id", required=True, help="价格方案ID")
    p_price.add_argument("--rooms", type=int, default=1, help="房间数量 (默认1)")
    p_price.add_argument("--room-count", type=int, help="同 --rooms")
    p_price.add_argument("--check-in-date", required=True, help="入住日期 YYYY-MM-DD")
    p_price.add_argument("--check-out-date", required=True, help="离店日期 YYYY-MM-DD")
    p_price.add_argument("--adults", type=int, default=2, help="每间房成人数 (默认2)")
    p_price.add_argument("--adult-count", type=int, help="同 --adults")
    p_price.add_argument("--children", type=int, default=0, help="每间房儿童数 (默认0)")
    p_price.add_argument("--child-count", type=int, help="同 --children")
    p_price.add_argument("--child-ages", help="儿童年龄，逗号分隔，如 3,5")
    p_price.add_argument("--child-age", help="同 --child-ages")

    # 5. book
    p_book = subparsers.add_parser("book", help="提交预订并生成收银台支付链接")
    p_book.add_argument("--reference-no", required=True, help="锁价凭证号")
    p_book.add_argument("--first-name", help="联系人名（拼音，缺省取首位客人名）")
    p_book.add_argument("--last-name", help="联系人姓（拼音，缺省取首位客人姓）")
    p_book.add_argument("--email", required=True, help="联系邮箱")
    p_book.add_argument("--guests", help="客人信息: 房号,名,姓,是否成人[,年龄] (分号分隔多个，如 1,SAN,ZHANG,true;1,XIAO,ZHANG,false,6)")
    p_book.add_argument("--guest", help="同 --guests")
    p_book.add_argument("--customer-request", help="客户特殊要求备注")
    p_book.add_argument("--request", help="同 --customer-request")

    # 6. orders
    p_orders = subparsers.add_parser("orders", help="查询订单列表")
    p_orders.add_argument("--status", "-s", choices=["ALL", "PENDING", "FINISHED"], default="ALL", help="订单状态筛选 (默认ALL)")
    p_orders.add_argument("--start-date", help="下单起始日期 YYYY-MM-DD")
    p_orders.add_argument("--end-date", help="下单结束日期 YYYY-MM-DD")

    # 7. order detail
    p_ord_detail = subparsers.add_parser("order-detail", help="查询单笔订单详情")
    p_ord_detail.add_argument("order_no_pos", nargs="?", help="订单号（位置参数）")
    p_ord_detail.add_argument("--order-no", help="订单号（选项参数）")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    mapping = {
        "hotel-tags": cmd_tags,
        "search-hotels": cmd_search,
        "hotel-detail": cmd_detail,
        "price-confirm": cmd_price_confirm,
        "book": cmd_book,
        "orders": cmd_orders,
        "order-detail": cmd_order_detail,
    }
    mapping[args.command](args)

if __name__ == "__main__":
    main()
