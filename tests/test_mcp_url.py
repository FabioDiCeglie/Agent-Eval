from __future__ import annotations

import pytest

from mcp_client import MCPClient, resolve_mcp_url, strip_mcp_url


def test_resolve_requires_url() -> None:
    with pytest.raises(ValueError, match="--mcp-url"):
        resolve_mcp_url(None)


def test_resolve_ignores_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "https://env.example.com")
    monkeypatch.setenv("MCP_GATEWAY_URL", "http://localhost:8080")
    with pytest.raises(ValueError, match="--mcp-url"):
        resolve_mcp_url(None)


def test_normalize_appends_mcp_suffix() -> None:
    assert resolve_mcp_url("https://host.example.com/v1") == (
        "https://host.example.com/v1/mcp"
    )


def test_normalize_preserves_existing_mcp_path() -> None:
    assert (
        resolve_mcp_url("https://host.example.com/mcp")
        == "https://host.example.com/mcp"
    )


def test_client_uses_explicit_url() -> None:
    client = MCPClient(mcp_url="https://client.example.com/base")
    assert client.mcp_url == "https://client.example.com/base/mcp"


def test_strip_mcp_url() -> None:
    assert strip_mcp_url("  http://x  ") == "http://x"
    assert strip_mcp_url("") is None
    assert strip_mcp_url(None) is None
