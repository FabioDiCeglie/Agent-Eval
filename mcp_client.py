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

DEFAULT_GATEWAY_URL = "http://localhost:8080/mcp"
DEFAULT_TIMEOUT_SEC = 60.0


def _normalize_gateway_url(url: str) -> str:
    url = url.rstrip("/")
    if not url.endswith("/mcp"):
        url = f"{url}/mcp"
    return url


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
    """Forwards tool calls to the MCP Gateway (Streamable HTTP + JWT from GATEWAY_JWT_SECRET)."""

    def __init__(
        self,
        gateway_url: str | None = None,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.gateway_url = _normalize_gateway_url(
            gateway_url or os.environ.get("MCP_GATEWAY_URL", DEFAULT_GATEWAY_URL)
        )
        self.token = _gateway_bearer_token()
        self.timeout_sec = timeout_sec

        self._stack: contextlib.AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._connect_lock = asyncio.Lock()
        self.last_roundtrip_ms: float = 0.0

    @classmethod
    def from_env(cls) -> MCPClient:
        return cls()

    async def call_tool(self, name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool through the gateway and return the result payload."""
        start = time.perf_counter()
        session = await self._ensure_connected()
        result = await session.call_tool(name, inputs)
        self.last_roundtrip_ms = (time.perf_counter() - start) * 1000
        return _format_call_tool_result(result)

    async def list_tools(self) -> list[Tool]:
        """Return tools exposed by the upstream MCP server (via the gateway)."""
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

            headers: dict[str, str] = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            stack = contextlib.AsyncExitStack()
            try:
                http_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=headers,
                        timeout=httpx.Timeout(self.timeout_sec),
                    )
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(self.gateway_url, http_client=http_client)
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
