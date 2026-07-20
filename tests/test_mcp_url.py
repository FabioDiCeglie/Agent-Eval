from __future__ import annotations

import pytest

from mcp_client import DEFAULT_MCP_URL, MCPClient, resolve_mcp_url


def test_resolve_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_URL", raising=False)
    monkeypatch.delenv("MCP_GATEWAY_URL", raising=False)
    assert resolve_mcp_url() == DEFAULT_MCP_URL


def test_mcp_url_env_wins_over_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "https://primary.example.com")
    monkeypatch.setenv("MCP_GATEWAY_URL", "http://localhost:8080")
    assert resolve_mcp_url() == "https://primary.example.com/mcp"


def test_gateway_fallback_when_mcp_url_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCP_URL", raising=False)
    monkeypatch.setenv("MCP_GATEWAY_URL", "http://localhost:9090")
    assert resolve_mcp_url() == "http://localhost:9090/mcp"


def test_explicit_arg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "https://env.example.com")
    assert resolve_mcp_url("https://cli.example.com") == "https://cli.example.com/mcp"


def test_normalize_appends_mcp_suffix() -> None:
    assert resolve_mcp_url("https://host.example.com/v1") == "https://host.example.com/v1/mcp"


def test_normalize_preserves_existing_mcp_path() -> None:
    assert (
        resolve_mcp_url("https://host.example.com/mcp")
        == "https://host.example.com/mcp"
    )


def test_client_uses_resolved_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "https://client.example.com/base")
    client = MCPClient.from_env()
    assert client.mcp_url == "https://client.example.com/base/mcp"
