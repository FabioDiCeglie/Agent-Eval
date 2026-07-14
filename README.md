# agent-eval

A test suite for Claude agents, where tests are written in YAML.

You define what Claude should do and what counts as passing — agent-eval runs it and reports pass/fail, cost, and latency.

## How it works

```
You write a YAML task:
  prompt: "Search Wikipedia for the Eiffel Tower"
  tools_allowed: [wikipedia_search]
  success_criteria:
    type: contains_substring
    value: "Paris"
```

```
agent-eval runs it:

  1. Sends prompt ──────────────────► Anthropic API (Claude)
                                            │
  2. Claude calls a tool ◄─────────────────┘
            │
  3. Forwards tool call ────────────► MCP Gateway (tool execution)
            │                               │
  4. Tool result back ◄────────────────────┘
            │
  5. Claude writes final response
            │
  6. Evaluator checks the response
            │
       pass ✓ or fail ✗
       + cost, latency, token usage
```

```
User's YAML task
      │
      ▼
   Runner  ◄──────────────────────────────────────────────────┐
      │                                                        │
      ├──► Anthropic API  →  Claude thinks, decides            │
      │         │                                              │
      │    Claude says "call tool X"                           │
      │         │                                              │
      └──► MCP Gateway  →  tool executes  →  result ──────────┘
                                    (loop until Claude is done)
      │
      ▼
  Evaluator  →  pass / fail
      │
      ▼
  TaskResult  (tokens, cost, latency, score)
```

**What gets evaluated:** Claude's reasoning, tool use decisions, and answer quality.

**Not evaluated here:** Whether the MCP Gateway is working correctly — that's the gateway's own concern (it has its own auth, rate limiting, audit logs, and tracing).

## Setup

```bash
uv sync --all-groups
cp .env.example .env  # fill in your API keys

# install the git pre-commit hook (one-time)
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```



## Usage

```bash
# Text-only task (no gateway needed)
uv run agent-eval run tasks/example.yaml

# Tool task — start the gateway first, then run
./scripts/mcp-up.sh
uv run agent-eval run tasks/mcp_example.yaml
```

### MCP Gateway setup

1. Start the gateway: `./scripts/mcp-up.sh`
2. Copy `config/mcp-gateway.env.example` values — the gateway creates `.mcp-gateway/.env` on first run
3. Sign a JWT for agent-eval (same secret as `GATEWAY_JWT_SECRET`):

```bash
uv run python - <<'EOF'
import os, time, jwt
secret = "your-secret-at-least-32-chars-long"  # match gateway .env
print(jwt.encode({"sub": "agent-eval", "iat": int(time.time()), "exp": int(time.time()) + 3600}, secret, algorithm="HS256"))
EOF
```

4. Put the token in `.env` as `MCP_GATEWAY_TOKEN`

The demo gateway only allows the `echo` tool (see MCP-Gateway `policy.yaml`). Tasks declare which tools Claude may use via `tools_allowed` in YAML.

