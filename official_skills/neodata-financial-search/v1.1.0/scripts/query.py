#!/usr/bin/env python3
"""NeoData 金融数据查询客户端（公网域名 + Bearer 短效 Token 鉴权）

Usage:
    python query.py --query "腾讯最新财报"
    python query.py --query "贵州茅台股价" --data-type api
    python query.py --query "腾讯最新财报" --signals stock
    python query.py --query "黄金价格" --signals commodity
    python query.py --query "腾讯最新财报" --return-raw-json

Token:
    默认用本文件内的 DEFAULT_TOKEN，调用方无需做任何配置。
    仅当需要临时换 token 时，设环境变量 NEODATA_TOKEN 或 NEODATA_API_KEY 覆盖。

    不再从 .neodata_token 这类文件读取：点文件在打包安装时会被丢掉，形同虚设；
    而 ~/.workbuddy/ 下的同名文件是另一个 skill 的缓存，内容是 JSON，
    被误读成 token 发出去只会得到一句「token 无效」，反而把人引向错误方向。
"""

import argparse
import json
import os
import sys
import uuid
from typing import List, Optional

try:
    import requests
except ImportError:
    print("需要安装 requests: pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_BASE_URL = "https://lily.tencent.com/neodata/query"
CHANNEL = "neodata"
SUB_CHANNEL = "workbuddy"

# NeoData 下发的公网 token，所有安装共用这一份。失效后需要重新发布本文件。
DEFAULT_TOKEN = "nd-P8rAD5uQpgzgxMs1DrCozjns43qpqSmNZCRoF1vbPQ4qOqJ3"

VALID_SIGNALS = (
    "kline",
    "stock",
    "index",
    "sector",
    "bond",
    "fund",
    "futures",
    "option",
    "macro",
    "forex",
    "commodity",
    "news"
)

# 网关层 401/403 之外，NeoData 在 HTTP 200 响应体内用业务码表达鉴权失败
AUTH_ERROR_CODES = {"1616039111"}
AUTH_ERROR_KEYWORDS = ("token", "鉴权", "授权", "凭证", "unauthor")

AUTH_HINT = (
    "鉴权失败（HTTP {code}）。可临时设环境变量 NEODATA_TOKEN=<新token> 重试；"
    "若无可用 token，请向 NeoData 侧申请。"
)


def detect_auth_failure(result: dict) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    code = str(result.get("code", "")).strip()
    msg = str(result.get("msg", "")).strip()
    if code in AUTH_ERROR_CODES:
        return f"code={code} msg={msg or 'token 无效或不存在'}"
    if result.get("suc") is False:
        low = msg.lower()
        if any(k in low for k in AUTH_ERROR_KEYWORDS):
            return f"code={code} msg={msg}"
    return None


class NeodataAuthError(RuntimeError):
    pass


def resolve_token() -> tuple:
    """默认用内置 token，环境变量是唯一的临时覆盖入口。"""
    for var in ("NEODATA_TOKEN", "NEODATA_API_KEY"):
        value = os.environ.get(var, "").strip()
        if value:
            return value, f"环境变量 {var}"
    return DEFAULT_TOKEN, "脚本内置 token"


def parse_signals(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    seen = []
    for part in raw.replace(";", ",").split(","):
        name = part.strip().lower()
        if name in VALID_SIGNALS and name not in seen:
            seen.append(name)
    return seen


def query_neodata(
    query: str,
    data_type: str = "all",
    request_id: Optional[str] = None,
    signals: Optional[List[str]] = None,
    return_raw_json: bool = False,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    url = base_url or os.environ.get("NEODATA_BASE_URL", "").strip() or DEFAULT_BASE_URL
    if token is None:
        token, _ = resolve_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "channel": CHANNEL,
        "sub_channel": SUB_CHANNEL,
        "query": query,
        "request_id": request_id or uuid.uuid4().hex,
        "data_type": data_type
    }
    if signals:
        payload["signal"] = {"type_list": signals}
    if return_raw_json:
        payload["return_raw_json"] = True

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code in (401, 403):
        raise NeodataAuthError(AUTH_HINT.format(code=resp.status_code))
    resp.raise_for_status()
    result = resp.json()
    auth_error = detect_auth_failure(result)
    if auth_error:
        raise NeodataAuthError(
            "NeoData 公网 token 不可用（{}）。服务端会区分「token不存在 / 已失效 / "
            "使用次数已耗尽 / 已过期」，按上面的 msg 找 NeoData 侧处理；"
            "手上有可用 token 时，设环境变量 NEODATA_TOKEN=<新token> 可临时绕过。".format(auth_error)
        )
    return result


def main():
    parser = argparse.ArgumentParser(description="NeoData 金融数据查询")
    parser.add_argument("--query", "-q", default=None, help="自然语言查询")
    parser.add_argument("--data-type", "-d", default="all", choices=["all", "api", "doc"], help="数据类型")
    parser.add_argument("--request-id", default=None, help="请求ID (默认自动生成)")
    parser.add_argument(
        "--signals",
        "--signal",
        "--signal.type_list",
        dest="signals",
        default=None,
        help="数据源signal，逗号分隔，如stock或stock,news",
    )
    parser.add_argument(
        "--return-raw-json",
        action="store_true",
        default=False,
        help="响应中附带结构化数据的原始 JSON",
    )
    parser.add_argument("--debug-auth", action="store_true", help="打印 token 来源（脱敏）后退出")

    args = parser.parse_args()

    if args.debug_auth:
        token, source = resolve_token()
        masked = token[:6] + "..." + token[-4:] if len(token) > 12 else "***"
        print(json.dumps({"token_source": source, "token_masked": masked}, ensure_ascii=False, indent=2))
        return

    if not args.query:
        parser.error("缺少 --query 参数")

    signals = parse_signals(args.signals)

    try:
        result = query_neodata(
            query=args.query,
            data_type=args.data_type,
            request_id=args.request_id,
            signals=signals,
            return_raw_json=args.return_raw_json,
        )
    except NeodataAuthError as e:
        print(f"鉴权错误: {e}", file=sys.stderr)
        sys.exit(2)
    except requests.RequestException as e:
        print(f"请求失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
