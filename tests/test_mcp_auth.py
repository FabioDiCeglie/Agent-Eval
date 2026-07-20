from __future__ import annotations

import jwt
import pytest

from mcp_client import build_mcp_http_headers


def test_no_auth_env_returns_empty_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GATEWAY_JWT_SECRET", raising=False)
    monkeypatch.delenv("MCP_HEADERS", raising=False)
    assert build_mcp_http_headers() == {}


def test_mcp_auth_token_sets_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "static-token")
    monkeypatch.delenv("GATEWAY_JWT_SECRET", raising=False)
    headers = build_mcp_http_headers()
    assert headers == {"Authorization": "Bearer static-token"}


def test_gateway_jwt_when_no_mcp_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-secret-at-least-32-characters-long"
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("GATEWAY_JWT_SECRET", secret)
    headers = build_mcp_http_headers()
    assert "Authorization" in headers
    token = headers["Authorization"].removeprefix("Bearer ")
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    assert payload["sub"] == "agent-eval"


def test_mcp_auth_token_overrides_gateway_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "prefer-this")
    monkeypatch.setenv("GATEWAY_JWT_SECRET", "test-secret-at-least-32-characters-long")
    headers = build_mcp_http_headers()
    assert headers["Authorization"] == "Bearer prefer-this"


def test_mcp_headers_merged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GATEWAY_JWT_SECRET", raising=False)
    monkeypatch.setenv("MCP_HEADERS", '{"X-Api-Key":"abc","X-Trace":"1"}')
    headers = build_mcp_http_headers()
    assert headers == {"X-Api-Key": "abc", "X-Trace": "1"}


def test_bearer_overrides_authorization_in_mcp_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "from-env")
    monkeypatch.setenv(
        "MCP_HEADERS",
        '{"Authorization":"Bearer stale","X-Api-Key":"k"}',
    )
    headers = build_mcp_http_headers()
    assert headers["Authorization"] == "Bearer from-env"
    assert headers["X-Api-Key"] == "k"


def test_jwt_overrides_authorization_in_mcp_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-secret-at-least-32-characters-long"
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("GATEWAY_JWT_SECRET", secret)
    monkeypatch.setenv("MCP_HEADERS", '{"Authorization":"Bearer stale"}')
    headers = build_mcp_http_headers()
    token = headers["Authorization"].removeprefix("Bearer ")
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    assert payload["sub"] == "agent-eval"


def test_invalid_mcp_headers_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_HEADERS", "not-json")
    with pytest.raises(ValueError, match="MCP_HEADERS"):
        build_mcp_http_headers()
