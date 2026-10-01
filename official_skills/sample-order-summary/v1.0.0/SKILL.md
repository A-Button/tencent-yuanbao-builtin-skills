---
name: sample-order-summary
description: Calculate a read-only order subtotal, discount, shipping fee, and total from a local JSON file. Use when the user asks to verify or summarize order amounts from structured item data. Do not use to place, pay for, cancel, or modify an order.
version: v1.0.0
---

# Sample Order Summary

Use this Skill only for deterministic, read-only amount calculations.

## Workflow

1. Confirm the user supplied a JSON file containing `items`.
2. Run `python3 scripts/calculate_summary.py <input-json-path>`.
3. Return the calculated subtotal, discount, shipping fee, and total.
4. If validation fails, report the exact invalid field and stop. Do not guess missing prices or quantities.

## Input

The JSON object accepts:

- `items`: non-empty array of `{name, unitPrice, quantity}`.
- `discount`: optional non-negative number, default `0`.
- `shippingFee`: optional non-negative number, default `0`.

## Safety boundary

- Treat the operation as read-only.
- Do not access files other than the path supplied for this task.
- Do not place orders, initiate payment, or call external services.

