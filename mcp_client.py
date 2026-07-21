from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import Any

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, Tool

DEFAULT_TIMEOUT_SEC = 60.0


def _normalize_mcp_url(url: str) -> str:
    had_trailing_slash = url.endswith("/")
    url = url.rstrip("/")
    if not url.endswith("/mcp"):
        url = f"{url}/mcp"
    if had_trailing_slash:
        url = f"{url}/"
    return url


def strip_mcp_url(url: str | None) -> str | None:
    if url is None:
        return None
    value = str(url).strip()
    return value or None


def resolve_mcp_url(url: str | None) -> str:
    """Normalize MCP endpoint URL (--mcp-url only; no env or YAML fallback)."""
    explicit = strip_mcp_url(url)
    if not explicit:
        raise ValueError(
            "MCP URL is required: pass --mcp-url on the command line."
        )
    return _normalize_mcp_url(explicit)


def _gateway_bearer_token() -> str | None:
    secret = os.environ.get("GATEWAY_JWT_SECRET", "").strip()
    if not secret:
        return None
    now = int(time.time())
    return jwt.encode(
        {"sub": "agent-eval", "iat": now, "exp": now + 3600},
        secret,
        algorithm="HS256",
    )


def _resolve_bearer_token() -> str | None:
    """MCP_AUTH_TOKEN wins over JWT minted from GATEWAY_JWT_SECRET."""
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if token:
        return token
    return _gateway_bearer_token()


def build_mcp_http_headers() -> dict[str, str]:
    """HTTP headers for the Streamable HTTP MCP session (Bearer from env)."""
    bearer = _resolve_bearer_token()
    if not bearer:
        return {}
    return {"Authorization": f"Bearer {bearer}"}


def _format_call_tool_result(result: CallToolResult) -> dict[str, Any]:
    parts: list[str] = []
    for block in result.content:
        if block.type == "text":
            parts.append(block.text)

    payload: dict[str, Any] = {
        "content": "\n".join(parts),
        "is_error": result.isError,
    }
    if result.structuredContent is not None:
        payload["structured"] = result.structuredContent
    return payload


class MCPClient:
    """Streamable HTTP MCP client (MCP_AUTH_TOKEN or gateway JWT)."""

    def __init__(
        self,
        mcp_url: str | None = None,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.mcp_url = resolve_mcp_url(mcp_url)
        self._http_headers = build_mcp_http_headers()
        self.timeout_sec = timeout_sec

        self._stack: contextlib.AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._connect_lock = asyncio.Lock()
        self.last_roundtrip_ms: float = 0.0

    async def call_tool(self, name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool on the MCP server and return the result payload."""
        start = time.perf_counter()
        session = await self._ensure_connected()
        result = await session.call_tool(name, inputs)
        self.last_roundtrip_ms = (time.perf_counter() - start) * 1000
        return _format_call_tool_result(result)

    async def list_tools(self) -> list[Tool]:
        """Return tools exposed by the connected MCP server."""
        session = await self._ensure_connected()
        response = await session.list_tools()
        return response.tools

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    async def _ensure_connected(self) -> ClientSession:
        if self._session is not None:
            return self._session

        async with self._connect_lock:
            if self._session is not None:
                return self._session

            stack = contextlib.AsyncExitStack()
            try:
                http_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=self._http_headers,
                        timeout=httpx.Timeout(self.timeout_sec),
                        follow_redirects=True,
                    )
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(self.mcp_url, http_client=http_client)
                )
                session = await stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()
            except Exception:
                await stack.aclose()
                raise

            self._stack = stack
            self._session = session
            return session
