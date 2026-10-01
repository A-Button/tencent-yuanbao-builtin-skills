#!/usr/bin/env python3
"""Deterministic App-facing actions backed by the Luckin MCP server."""

from __future__ import annotations

import json
import math
import sys
from typing import Any

from cli_contract import ContractError, validate_operation
from mcp_client import MCPClient, MCPError


class CoffeeActionError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _required(args: dict, *names: str) -> None:
    missing = [name for name in names if args.get(name) in (None, "", [])]
    if missing:
        raise CoffeeActionError("INVALID_ARGUMENT", f"缺少参数：{', '.join(missing)}")


def _pickup_only(args: dict) -> None:
    if args.get("delivery") not in (None, "", "pick"):
        raise CoffeeActionError("PICKUP_ONLY", "目前仅支持到店自取。")


def _with_shop(payload: dict, args: dict) -> dict:
    """把调用方带入的门店回显进结果，让商品/定制页不依赖前序结果就能渲染。

    上游没有按 deptId 查门店的接口，门店只能由调用方给：界面用当前选中门店，
    Agent 用 query_shops 返回的那一家。deptId 一律以本次调用的为准，避免回显
    与实际查询的门店对不上。
    """
    shop = args.get("shop")
    if not isinstance(shop, dict):
        return payload
    echo = {"deptId": args["deptId"]}
    for field in ("deptName", "address", "longitude", "latitude"):
        value = shop.get(field)
        if value not in (None, ""):
            echo[field] = value
    payload["shop"] = echo
    return payload


def _normalize_products(items: Any) -> list[dict] | None:
    if not isinstance(items, list) or not items:
        return None
    result = []
    for item in items:
        if not isinstance(item, dict):
            return None
        try:
            product_id = item.get("productId", item.get("id"))
            sku_code = item.get("skuCode", item.get("sku"))
            amount = item.get("amount", item.get("skuNum"))
            if isinstance(product_id, bool) or isinstance(amount, bool):
                return None
            if int(product_id) != float(product_id) or int(amount) != float(amount):
                return None
            normalized = {
                "productId": int(product_id),
                "skuCode": str(sku_code or "").strip(),
                "amount": int(amount),
            }
        except (TypeError, ValueError):
            return None
        if normalized["productId"] <= 0 or not normalized["skuCode"] or not 1 <= normalized["amount"] <= 20:
            return None
        result.append(normalized)
    return result


def _product_signature(items: Any) -> list[tuple[int, str, int]] | None:
    normalized = _normalize_products(items)
    if normalized is None:
        return None
    return sorted((item["productId"], item["skuCode"], item["amount"]) for item in normalized)


def _money(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _submit_order(args: dict, client: MCPClient) -> dict:
    _pickup_only(args)
    _required(args, "deptId", "productList", "longitude", "latitude", "maxPayable")
    normalized_products = _normalize_products(args["productList"])
    if normalized_products is None:
        raise CoffeeActionError("INVALID_ARGUMENT", "商品明细格式不正确。")
    if len(normalized_products) != 1:
        raise CoffeeActionError("SINGLE_PRODUCT_ONLY", "当前仅支持单商品多杯下单。")
    requested_products = _product_signature(normalized_products)

    preview = client.call_tool("previewOrder", {
        "deptId": args["deptId"],
        "productList": normalized_products,
    })
    preview_products = _product_signature(
        preview.get("productInfoList", preview.get("productList"))
    )
    payable = _money(preview.get("discountPrice"))
    maximum = _money(args.get("maxPayable"))
    if preview_products is None or payable is None or maximum is None:
        return {
            "phase": "reconfirm",
            "reason": "PREVIEW_INCOMPLETE",
            "message": "订单预览信息不完整，尚未创建订单。",
            "preview": preview,
        }
    if preview_products != requested_products:
        return {
            "phase": "reconfirm",
            "reason": "PRODUCT_CHANGED",
            "message": "商品或规格发生变化，请重新确认。",
            "preview": preview,
        }
    if payable > maximum:
        return {
            "phase": "reconfirm",
            "reason": "PRICE_INCREASED",
            "message": "最终应付金额高于已确认价格，请重新确认。",
            "preview": preview,
            "maxPayable": maximum,
        }
    if (
        "couponCodeList" in preview
        and (
            not isinstance(preview["couponCodeList"], list)
            or any(not isinstance(item, str) or not item.strip() for item in preview["couponCodeList"])
        )
    ):
        return {
            "phase": "reconfirm",
            "reason": "COUPON_INVALID",
            "message": "优惠券信息异常，尚未创建订单。",
            "preview": preview,
        }

    create_args = {
        "deptId": args["deptId"],
        "productList": normalized_products,
        "longitude": args["longitude"],
        "latitude": args["latitude"],
    }
    coupons = preview.get("couponCodeList")
    if isinstance(coupons, list) and coupons:
        create_args["couponCodeList"] = coupons
    try:
        order = client.call_tool("createOrder", create_args)
    except MCPError:
        return {
            "phase": "error",
            "code": "ORDER_RESULT_UNCERTAIN",
            "message": "订单创建结果暂时无法确认，请先在瑞幸 App 中核验，避免重复下单。",
            "retryable": False,
        }
    return {
        "phase": "payment",
        "preview": preview,
        "order": order,
    }


def execute(operation: str, args: dict, client: MCPClient) -> dict:
    if not isinstance(args, dict):
        raise CoffeeActionError("INVALID_ARGUMENT", "请求参数必须为对象。")
    try:
        args = validate_operation(operation, args, agent_call=False)
    except ContractError as exc:
        raise CoffeeActionError("INVALID_ARGUMENT", str(exc)) from exc
    _pickup_only(args)

    if operation == "query_shops":
        _required(args, "longitude", "latitude")
        params = {
            "longitude": args["longitude"],
            "latitude": args["latitude"],
        }
        if args.get("deptName"):
            params["deptName"] = args["deptName"]
        return {
            "phase": "shops",
            "data": client.call_tool("queryShopList", params),
            "location": {
                "longitude": args["longitude"],
                "latitude": args["latitude"],
            },
            "filter": args.get("deptName", ""),
        }

    if operation == "search_products":
        _required(args, "deptId", "query")
        return _with_shop({
            "phase": "products",
            "deptId": args["deptId"],
            "query": args["query"],
            "data": client.call_tool("searchProductForMcp", {
                "deptId": args["deptId"],
                "query": args["query"],
            }),
        }, args)

    if operation == "product_detail":
        _required(args, "deptId", "productId")
        return _with_shop({
            "phase": "customize",
            "deptId": args["deptId"],
            "productId": args["productId"],
            "data": client.call_tool("queryProductDetailInfo", {
                "deptId": args["deptId"],
                "productId": args["productId"],
            }),
        }, args)

    if operation == "switch_product":
        _required(args, "deptId", "productId", "skuCode", "attrOperationParam", "amount")
        return _with_shop({
            "phase": "customize",
            "deptId": args["deptId"],
            "productId": args["productId"],
            "data": client.call_tool("switchProduct", {
                "deptId": args["deptId"],
                "productId": args["productId"],
                "skuCode": args["skuCode"],
                "attrOperationParam": args["attrOperationParam"],
                "amount": args["amount"],
            }),
        }, args)

    if operation == "submit_order":
        return _submit_order(args, client)

    if operation == "query_order":
        _required(args, "orderId")
        return {
            "phase": "order",
            "data": client.call_tool("queryOrderDetailInfo", {"orderId": args["orderId"]}),
        }

    if operation == "cancel_order":
        _required(args, "orderId")
        return {
            "phase": "order",
            "cancelled": True,
            "data": client.call_tool("cancelOrder", {"orderId": args["orderId"]}),
        }

    raise CoffeeActionError("UNKNOWN_OPERATION", f"不支持的操作：{operation}")


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    operation = ""
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise CoffeeActionError("INVALID_ARGUMENT", "请求参数必须为对象。")
        operation = args.pop("operation", "")
        result = execute(operation, args, MCPClient())
    except (json.JSONDecodeError, CoffeeActionError, MCPError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", "请求参数不是合法 JSON。")
        result = {
            "phase": "error",
            "code": code,
            "message": message,
            "retryable": code not in {"TOKEN_REQUIRED", "AUTH_FAILED", "ORDER_RESULT_UNCERTAIN"},
        }
    result.setdefault("operation", operation)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())