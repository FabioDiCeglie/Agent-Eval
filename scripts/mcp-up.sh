#!/usr/bin/env bash
# Clone MCP-Gateway and start its docker stack.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLONE_DIR="${MCP_GATEWAY_DIR:-$ROOT/.mcp-gateway}"
REPO_URL="${MCP_GATEWAY_REPO:-https://github.com/FabioDiCeglie/MCP-Gateway.git}"
ENV_TEMPLATE="$ROOT/config/mcp-gateway.env.example"
ENV_FILE="$CLONE_DIR/.env"
COMPOSE_FILE="$CLONE_DIR/docker/docker-compose.yaml"

if [[ ! -d "$CLONE_DIR/.git" ]]; then
  echo "Cloning MCP Gateway into $CLONE_DIR"
  git clone "$REPO_URL" "$CLONE_DIR"
else
  git -C "$CLONE_DIR" pull --ff-only
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  echo "Created $ENV_FILE from config/mcp-gateway.env.example"
fi

docker compose -f "$COMPOSE_FILE" up -d "$@"

echo
echo "Gateway: http://localhost:8080/mcp"
echo "Stop:    ./scripts/mcp-down.sh"
