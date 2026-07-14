#!/usr/bin/env bash
set -euo pipefail

CLONE_DIR="${MCP_GATEWAY_DIR:-$(cd "$(dirname "$0")/.." && pwd)/.mcp-gateway}"
COMPOSE_FILE="$CLONE_DIR/docker/docker-compose.yaml"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "No local MCP Gateway clone found at $CLONE_DIR" >&2
  exit 1
fi

docker compose -f "$COMPOSE_FILE" down "$@"
