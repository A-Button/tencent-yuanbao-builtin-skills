#!/usr/bin/env python3
"""Compatibility entry for existing Bazi callers; new requests use chart_quick.py."""
import chart_quick
from chart_quick import (BRANCHES, SCHEMA_PATH, TOPICS, EngineError, parse_time,
                         plan, question_result, validate_schema, _after_delivery, _recover)


def run(request, output_dir=None):
    return chart_quick.run(request, output_dir, compact=False)


def main():
    return chart_quick.main(compact=False)

if __name__ == "__main__":
    raise SystemExit(main())
