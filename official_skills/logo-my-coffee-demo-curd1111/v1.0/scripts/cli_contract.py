"""Machine-readable contract for the My Coffee Agent CLI."""

from __future__ import annotations

from difflib import get_close_matches
from typing import Any


class ContractError(ValueError):
    pass


# 瑞幸上游没有「按 deptId 查门店」的接口（queryShopList 只认经纬度），门店信息
# 只能由调用方带入。带上之后每次结果都自带渲染所需的门店，子页面不再依赖前序
# 结果，历史重放和换端打开才能独立还原。
SHOP_ARG_HINT = (
    "shop 传 query_shops 返回的该门店对象（deptId/deptName/address/longitude/latitude），"
    "结果会原样回显，供界面独立渲染门店信息；不传则结果缺少门店，界面需依赖前序结果。"
)
SHOP_ARG_EXAMPLE = {
    "deptId": 53901,
    "deptName": "中关村大街店",
    "address": "海淀区中关村大街 1 号",
    "longitude": 116.316037,
    "latitude": 39.983918,
}
SHOP_ECHO_FIELD = "{deptId, deptName, address, longitude, latitude}（仅在入参带 shop 时出现）"


OPERATIONS: dict[str, dict[str, Any]] = {
    "query_shops": {
        "description": "按精确经纬度查询门店。",
        "required": ["longitude", "latitude"],
        "optional": ["deptName"],
        "types": {"longitude": "number", "latitude": "number", "deptName": "string"},
        "outputPhases": ["shops"],
        "agentAllowed": True,
        "triggersUiUpdate": True,
        "example": {
            "operation": "query_shops",
            "longitude": 116.316037,
            "latitude": 39.983918,
            "deptName": "中关村",
        },
    },
    "search_products": {
        "description": f"在已确认门店中搜索商品。{SHOP_ARG_HINT}",
        "required": ["deptId", "query"],
        "optional": ["delivery", "amount", "shop"],
        "types": {
            "deptId": "integer",
            "query": "string",
            "delivery": "string",
            "amount": "integer",
            "shop": "object",
        },
        "outputPhases": ["products"],
        "agentAllowed": True,
        "triggersUiUpdate": True,
        "example": {
            "operation": "search_products",
            "deptId": 53901,
            "query": "拿铁",
            "shop": dict(SHOP_ARG_EXAMPLE),
        },
    },
    "product_detail": {
        "description": f"查询商品详情与可选规格。{SHOP_ARG_HINT}",
        "required": ["deptId", "productId"],
        "optional": ["delivery", "shop"],
        "types": {
            "deptId": "integer",
            "productId": "integer",
            "delivery": "string",
            "shop": "object",
        },
        "outputPhases": ["customize"],
        "agentAllowed": True,
        "triggersUiUpdate": True,
        "example": {
            "operation": "product_detail",
            "deptId": 53901,
            "productId": 5543,
            "shop": dict(SHOP_ARG_EXAMPLE),
        },
    },
    "switch_product": {
        "description": f"按属性变更解析真实 SKU 与价格。{SHOP_ARG_HINT}",
        "required": ["deptId", "productId", "skuCode", "attrOperationParam", "amount"],
        "optional": ["shop"],
        "types": {
            "deptId": "integer",
            "productId": "integer",
            "skuCode": "string",
            "attrOperationParam": "object",
            "amount": "integer",
            "shop": "object",
        },
        "outputPhases": ["customize"],
        "agentAllowed": True,
        "triggersUiUpdate": True,
        "example": {
            "operation": "switch_product",
            "deptId": 53901,
            "productId": 5543,
            "skuCode": "SP3963-00173",
            "attrOperationParam": {
                "attributeId": 64,
                "subAttr": {"attributeId": 594, "operation": 3},
            },
            "amount": 1,
        },
    },
    "submit_order": {
        "description": "预览、校验并创建自提订单，仅 App 页面可调用。",
        "required": ["deptId", "productList", "longitude", "latitude", "maxPayable"],
        "optional": ["delivery"],
        "types": {
            "deptId": "integer",
            "productList": "array",
            "longitude": "number",
            "latitude": "number",
            "maxPayable": "number",
            "delivery": "string",
        },
        "outputPhases": ["reconfirm", "payment", "error"],
        "agentAllowed": False,
        "triggersUiUpdate": False,
        "example": {
            "operation": "submit_order",
            "deptId": 53901,
            "productList": [{"amount": 1, "productId": 5543, "skuCode": "SP3963-00173"}],
            "longitude": 116.315599,
            "latitude": 39.983425,
            "maxPayable": 13.9,
        },
    },
    "query_order": {
        "description": "查询订单状态，仅 App 页面可调用。",
        "required": ["orderId"],
        "optional": [],
        "types": {"orderId": "string"},
        "outputPhases": ["order"],
        "agentAllowed": False,
        "triggersUiUpdate": False,
        "example": {"operation": "query_order", "orderId": "example-order-id"},
    },
    "cancel_order": {
        "description": "取消订单，仅 App 页面可调用。",
        "required": ["orderId"],
        "optional": [],
        "types": {"orderId": "string"},
        "outputPhases": ["order"],
        "agentAllowed": False,
        "triggersUiUpdate": False,
        "example": {"operation": "cancel_order", "orderId": "example-order-id"},
    },
}

FIELD_SUGGESTIONS = {
    "keyword": "query",
    "shopId": "deptId",
}

OUTPUTS = {
    "query_shops": {
        "fields": {
            "operation": "query_shops",
            "phase": "shops",
            "data": "array of shops",
            "location": "{longitude, latitude}",
            "filter": "string",
        }
    },
    "search_products": {
        "fields": {
            "operation": "search_products",
            "phase": "products",
            "deptId": "integer",
            "query": "string",
            "data": "array of products",
            "shop": SHOP_ECHO_FIELD,
        }
    },
    "product_detail": {
        "fields": {
            "operation": "product_detail",
            "phase": "customize",
            "deptId": "integer",
            "productId": "integer",
            "data": "product detail object",
            "shop": SHOP_ECHO_FIELD,
        }
    },
    "switch_product": {
        "fields": {
            "operation": "switch_product",
            "phase": "customize",
            "deptId": "integer",
            "productId": "integer",
            "data": "updated product/SKU object",
            "shop": SHOP_ECHO_FIELD,
        }
    },
    "submit_order": {
        "fields": {
            "operation": "submit_order",
            "phase": "reconfirm | payment | error",
            "preview": "order preview object",
            "order": "created order object (payment)",
            "reason": "reconfirm reason (reconfirm)",
        }
    },
    "query_order": {
        "fields": {
            "operation": "query_order",
            "phase": "order",
            "data": "order detail object",
        }
    },
    "cancel_order": {
        "fields": {
            "operation": "cancel_order",
            "phase": "order",
            "cancelled": "boolean",
            "data": "cancel result object",
        }
    },
}


def describe_contract() -> dict[str, Any]:
    operations = {
        name: {**spec, "output": OUTPUTS[name]}
        for name, spec in OPERATIONS.items()
    }
    return {
        "app": "my-coffee",
        "invocation": "python3 /data/skills/my-coffee/scripts/_run.py coffee_api '<json>'",
        "describe": "python3 /data/skills/my-coffee/scripts/_run.py describe",
        "commonError": {
            "fields": {
                "operation": "string",
                "phase": "error",
                "code": "string",
                "message": "string",
                "retryable": "boolean",
            }
        },
        "scripts": [
            {
                "name": "coffee_api",
                "description": "瑞幸 App 的唯一 Agent CLI。",
                "operations": operations,
            }
        ],
    }


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return False


def validate_operation(operation: str, args: dict[str, Any], *, agent_call: bool) -> dict[str, Any]:
    spec = OPERATIONS.get(operation)
    if spec is None:
        raise ContractError(f"不支持的 operation：{operation}")
    if agent_call and not spec["agentAllowed"]:
        raise ContractError(f"Agent 不允许执行 operation：{operation}")
    if not isinstance(args, dict):
        raise ContractError("参数必须是对象")

    allowed = set(spec["required"]) | set(spec["optional"])
    unknown = sorted(set(args) - allowed)
    if unknown:
        messages = []
        for name in unknown:
            known = FIELD_SUGGESTIONS.get(name)
            suggestion = [known] if known in allowed else get_close_matches(name, sorted(allowed), n=1, cutoff=0.45)
            messages.append(f"{name} 是否应为 {suggestion[0]}" if suggestion else name)
        raise ContractError(f"不允许字段：{', '.join(messages)}")

    missing = [name for name in spec["required"] if args.get(name) in (None, "", [])]
    if missing:
        raise ContractError(f"缺少参数：{', '.join(missing)}")

    for name, value in args.items():
        expected = spec["types"].get(name)
        if expected and not _matches_type(value, expected):
            raise ContractError(f"{name} 必须是 {expected}")

    if "amount" in args and not 1 <= args["amount"] <= 20:
        raise ContractError("amount 必须是 1-20 的整数")
    return dict(args)