#!/usr/bin/env python3
"""Minimal, secret-safe Streamable HTTP client for the Luckin MCP server."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Mapping

try:
    from _credential import TOKEN as EMBEDDED_TOKEN
except ImportError:
    EMBEDDED_TOKEN = ""


DEFAULT_MCP_URL = "https://gwmcp.lkcoffee.com/order/user/mcp"
DEFAULT_TOKEN_PATH = Path.home() / ".my-coffee" / "LUCKIN_MCP_TOKEN"


class MCPError(RuntimeError):
    """Stable MCP failure that is safe to expose to the App UI."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_token(
    environ: Mapping[str, str] | None = None,
    token_path: Path = DEFAULT_TOKEN_PATH,
    embedded_token: str | None = None,
) -> str:
    env = os.environ if environ is None else environ
    token = (env.get("LUCKIN_MCP_TOKEN") or "").strip()
    if token:
        return token
    token = (EMBEDDED_TOKEN if embedded_token is None else embedded_token).strip()
    if token:
        return token
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if not token:
        raise MCPError(
            "TOKEN_REQUIRED",
            "请先配置 LUCKIN_MCP_TOKEN，或写入 ~/.my-coffee/LUCKIN_MCP_TOKEN。",
        )
    return token


def parse_mcp_response(body: bytes, content_type: str) -> dict:
    text = body.decode("utf-8", errors="replace").strip()
    if "text/event-stream" not in (content_type or "").lower():
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MCPError("MCP_PROTOCOL_ERROR", "瑞幸服务返回了无法识别的数据。") from exc
        if not isinstance(value, dict):
            raise MCPError("MCP_PROTOCOL_ERROR", "瑞幸服务返回格式不正确。")
        return value

    frames = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data_lines = [
            line[5:].lstrip()
            for line in block.splitlines()
            if line.startswith("data:")
        ]
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        if raw == "[DONE]":
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            frames.append(value)
    if not frames:
        raise MCPError("MCP_PROTOCOL_ERROR", "瑞幸服务未返回有效事件。")
    return frames[-1]


class MCPClient:
    def __init__(
        self,
        token: str | None = None,
        endpoint: str | None = None,
        timeout: float = 25.0,
        transport: Callable[[str, dict], dict] | None = None,
    ):
        self._token = token or load_token()
        self._endpoint = endpoint or os.environ.get("LUCKIN_MCP_URL") or DEFAULT_MCP_URL
        parsed_endpoint = urllib.parse.urlparse(self._endpoint)
        if parsed_endpoint.scheme != "https" or parsed_endpoint.hostname != "gwmcp.lkcoffee.com":
            raise MCPError("UNSAFE_ENDPOINT", "瑞幸 MCP 地址必须使用官方 HTTPS 域名。")
        self._timeout = timeout
        self._transport = transport or self._http_transport
        self._tools: dict[str, dict] | None = None
        self._request_id = 0

    def _http_transport(self, method: str, params: dict) -> dict:
        self._request_id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._request_id,
        }).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(
                request,
                timeout=self._timeout,
            ) as response:
                return parse_mcp_response(
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise MCPError("AUTH_FAILED", "瑞幸登录凭证无效或已过期。") from None
            if exc.code == 429:
                raise MCPError("RATE_LIMITED", "操作过于频繁，请稍后重试。") from None
            raise MCPError("MCP_HTTP_ERROR", f"瑞幸服务暂时不可用（HTTP {exc.code}）。") from None
        except (urllib.error.URLError, TimeoutError):
            raise MCPError("MCP_UNAVAILABLE", "暂时无法连接瑞幸服务，请稍后重试。") from None

    @staticmethod
    def _result(response: dict) -> dict:
        error = response.get("error")
        if error:
            raise MCPError("MCP_CALL_FAILED", "瑞幸服务未能完成本次操作。")
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPError("MCP_PROTOCOL_ERROR", "瑞幸服务缺少调用结果。")
        return result

    def _load_tools(self) -> dict[str, dict]:
        if self._tools is None:
            result = self._result(self._transport("tools/list", {}))
            tools = result.get("tools")
            if not isinstance(tools, list):
                raise MCPError("MCP_PROTOCOL_ERROR", "瑞幸服务未返回工具列表。")
            self._tools = {
                item["name"]: item
                for item in tools
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
        return self._tools

    @staticmethod
    def _business_data(value):
        if isinstance(value, dict) and isinstance(value.get("success"), bool):
            if not value["success"]:
                raise MCPError("MCP_CALL_FAILED", "瑞幸服务未能完成本次操作。")
            return value.get("data")
        return value

    def call_tool(self, name: str, arguments: dict):
        if name not in self._load_tools():
            raise MCPError("TOOL_UNAVAILABLE", f"瑞幸服务暂不支持 {name}。")
        result = self._result(self._transport(
            "tools/call",
            {"name": name, "arguments": arguments},
        ))
        if result.get("isError") is True:
            raise MCPError("MCP_CALL_FAILED", "瑞幸服务未能完成本次操作。")
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return self._business_data(structured)
        for item in result.get("content") or []:
            if not isinstance(item, dict) or item.get("type") != "text":
                continue
            text = item.get("text")
            if not isinstance(text, str):
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return self._business_data(value)
        raise MCPError("MCP_PROTOCOL_ERROR", "瑞幸服务未返回结构化业务数据。")
