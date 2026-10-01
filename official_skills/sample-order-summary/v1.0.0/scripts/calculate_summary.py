#!/usr/bin/env python3
"""Calculate a deterministic order summary from one local JSON file."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


def money(value: object, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return amount


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: calculate_summary.py <input-json-path>"}))
        return 2

    input_path = Path(sys.argv[1]).resolve()
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a non-empty array")

        normalized_items = []
        subtotal = Decimal("0")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"items[{index}] must be an object")
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"items[{index}].name must be a non-empty string")
            unit_price = money(item.get("unitPrice"), f"items[{index}].unitPrice")
            quantity = item.get("quantity")
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
                raise ValueError(f"items[{index}].quantity must be a positive integer")
            line_total = unit_price * quantity
            subtotal += line_total
            normalized_items.append({
                "name": name.strip(),
                "unitPrice": str(unit_price.quantize(Decimal("0.01"))),
                "quantity": quantity,
                "lineTotal": str(line_total.quantize(Decimal("0.01"))),
            })

        discount = money(payload.get("discount", 0), "discount")
        shipping_fee = money(payload.get("shippingFee", 0), "shippingFee")
        if discount > subtotal:
            raise ValueError("discount cannot exceed subtotal")
        total = subtotal - discount + shipping_fee

        result = {
            "ok": True,
            "items": normalized_items,
            "subtotal": str(subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "discount": str(discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "shippingFee": str(shipping_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "total": str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "currency": "CNY",
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

