# agent-eval — Plan

A YAML-based test runner for Claude agents. Define tasks, run them, get pass/fail with basic metrics.

---

## What it does

```
YAML task file  →  TaskRunner  →  Claude API  →  Evaluator  →  CLI report
                                      ↓
                               MCP Gateway (if tools_allowed)
```

1. Load tasks from a YAML file
2. Send each prompt to Claude (with optional tools)
3. Loop on tool calls until Claude finishes or `max_turns` is hit
4. Check the result against `success_criteria`
5. Print a pass/fail table with tokens and latency

---

## Task format

```yaml
tasks:
  - id: t001
    name: "Simple factual lookup"
    prompt: "What is the capital of France?"
    tools_allowed: []
    success_criteria:
      type: contains_substring
      value: "Paris"
    tags: [factual]
```

### Fields

| Field | Description |
|---|---|
| `id` | Unique task identifier |
| `name` | Human-readable label |
| `prompt` | Message sent to Claude |
| `tools_allowed` | Tool names Claude may call (empty = text-only) |
| `success_criteria` | How to decide pass/fail |
| `tags` | Optional labels for grouping |

### Success criteria

| Type | Fields | Description |
|---|---|---|
| `contains_substring` | `value` | Final response must contain the string |
| `regex_match` | `value` | Final response must match the regex |
| `tool_sequence` | `sequence` | Tool calls must appear in the given order |

---

## Architecture

```
main.py          CLI — loads YAML, runs tasks, prints results
runner.py        Turn loop — Claude API + tool forwarding
models.py        Pydantic models: Task, SuccessCriteria, TaskResult
mcp_client.py    Thin MCP Gateway client (Streamable HTTP)
evaluators/      contains_substring, regex_match, tool_sequence
tasks/           Example task files
scripts/         mcp-up.sh, mcp-down.sh, pre-commit hook
```

### Turn loop

```
1. POST /v1/messages  { model, messages, tools }
2. If stop_reason == "tool_use":
     a. Forward each tool call to MCP Gateway
     b. Append tool results to messages
     c. Go to 1
3. If stop_reason == "end_turn":
     a. Run success_criteria against final response
     b. Return TaskResult
```

### MCP Gateway

Tool tasks forward calls to an external [MCP Gateway](https://github.com/FabioDiCeglie/MCP-Gateway). agent-eval does not handle auth, rate limiting, or policy — that lives in the gateway.

Configuration (via `.env`):

- `MCP_GATEWAY_URL` — gateway endpoint (default `http://localhost:8080`)
- `MCP_GATEWAY_TOKEN` — JWT for gateway auth

Start the gateway with `./scripts/mcp-up.sh` before running tool tasks.

---

## Metrics per task

| Metric | Source |
|---|---|
| `passed` | Evaluator result |
| `turn_count` | Message roundtrips |
| `tool_call_count` | Total tool invocations |
| `tool_calls_by_name` | `{tool_name: count}` |
| `input_tokens` / `output_tokens` | API usage fields |
| `latency_total_ms` | Wall-clock time for the run |
| `error` | Set if the run crashed |

Suite-level: pass rate is printed at the end of a run.

---

## CLI

```bash
uv sync --all-groups
cp .env.example .env   # ANTHROPIC_API_KEY, MCP_GATEWAY_* if needed

uv run agent-eval run tasks/example.yaml
uv run agent-eval run tasks/mcp_example.yaml --model claude-haiku-4-5 --max-turns 10
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Claude SDK | `anthropic` (async) |
| CLI | `click` + `rich` |
| Models | `pydantic` |
| YAML | `pyyaml` |
| MCP client | `mcp` + `httpx` |
| Linting | `ruff` (pre-commit hook) |

---

## Folder structure

```
agent-eval/
├── main.py
├── runner.py
├── models.py
├── mcp_client.py
├── evaluators/
│   ├── base.py
│   ├── substring.py
│   ├── regex_eval.py
│   └── tool_sequence.py
├── tasks/
│   ├── example.yaml
│   └── mcp_example.yaml
├── config/
│   └── mcp-gateway.env.example
├── scripts/
│   ├── mcp-up.sh
│   ├── mcp-down.sh
│   └── pre-commit
├── pyproject.toml
├── .env.example
├── README.md
└── Plan.md
```

---

## Design decisions

**Flat layout** — no nested package; modules live at the repo root for simplicity.

**Deterministic evaluators only** — pass/fail is binary (substring, regex, tool order). No LLM-as-judge.

**MCP Gateway is external** — agent-eval only forwards tool calls and records what it observes. Gateway auth, policy, and audit are not reimplemented here.

**Sequential task runs** — tasks in a suite run one at a time. Parallel execution can be added later if needed.

**No persisted results** — output goes to the terminal. JSON export, baselines, and regression diffs are out of scope for now.

---

## Milestone 2.0 — Any MCP URL

**Goal:** agent-eval is a generic MCP client over Streamable HTTP. Users point at any MCP server URL; the MCP Gateway repo and demo tools are an optional local example, not the only supported backend.

### Target UX

```bash
uv run agent-eval run tasks/my_suite.yaml --mcp-url https://mcp.example.com/mcp
```

Or via `.env`:

```bash
MCP_URL=https://mcp.example.com/mcp
MCP_AUTH_TOKEN=...   # optional Bearer token
```

Text-only suites (`tools_allowed: []`) unchanged — no MCP connection.

### Problems in 1.x

- Tool schemas are hardcoded in `runner.py` (`echo`, `ping`) for the gateway demo server.
- Env and docs center on `MCP_GATEWAY_URL` + `GATEWAY_JWT_SECRET`.
- Per-task `tools_allowed` must stay in sync with gateway `policy.yaml` with no discovery.
- Other developers cannot plug in their own MCP without forking or editing Python.

### Work items

1. **Generic connection config**
   - Primary: `MCP_URL` (required when any task in the suite uses tools).
   - Optional: `MCP_AUTH_TOKEN` or `MCP_HEADERS` (JSON) for Bearer / API-key auth.
   - **Backward compatible:** if `MCP_URL` is unset, fall back to `MCP_GATEWAY_URL`; if `GATEWAY_JWT_SECRET` is set, keep minting JWT as today (gateway preset).

2. **Discover tools from the server**
   - At suite start: `list_tools()` on the MCP session.
   - Map MCP `Tool` → Anthropic tool definitions (`name`, `description`, `inputSchema`).
   - Per-task `tools_allowed`: filter that catalog (empty list = text-only task; non-empty = only those names exposed to Claude for that task).

3. **Remove hardcoded `_TOOL_DEFS`**
   - Delete demo-only schemas from `runner.py`; all tool metadata comes from the connected MCP server.

4. **CLI**
   - Add `--mcp-url` on `run`; overrides env / suite file.

5. **Optional suite-level YAML** (nice-to-have in 2.0)
   ```yaml
   mcp:
     url: https://mcp.example.com/mcp   # or rely on MCP_URL env
   tasks:
     - id: ...
   ```
   CLI `--mcp-url` wins over file; secrets stay in env, not committed YAML.

6. **Documentation**
   - Default path: “Connect any Streamable HTTP MCP server.”
   - Appendix: “Local gateway demo” (`./scripts/mcp-up.sh`, policy, JWT) as an integration example.

### Architecture (2.0)

```
YAML task file  →  TaskRunner  →  Claude API  →  Evaluator  →  CLI report
                                      ↓
                               MCP server (Streamable HTTP)
                               list_tools + call_tool
```

Gateway becomes one deployment of an MCP endpoint, not a separate product concept inside agent-eval.

### Turn loop change

```
1. POST /v1/messages  { model, messages, tools }   # tools from list_tools(), filtered by task
2. If stop_reason == "tool_use":
     a. Forward each tool call to MCP_URL
     b. Append tool results to messages
     c. Go to 1
3. If stop_reason == "end_turn":
     a. Run success_criteria against final response
     b. Return TaskResult
```

Policy / upstream allow-lists remain on the MCP server or gateway; agent-eval only filters what Claude is allowed to invoke per task.

### Out of scope for 2.0 (candidate 2.1+)

| Item | Notes |
|---|---|
| stdio MCP (“run this binary”) | Different transport; 2.0 is URL + Streamable HTTP only |
| Per-task different MCP URLs | One MCP connection per suite run is enough for most CI |
| Policy engine in agent-eval | Not reimplemented; stays external |
| Parallel task runs | Still sequential unless added explicitly later |

### Definition of done

- A new developer sets `ANTHROPIC_API_KEY` + `MCP_URL`, writes tasks using tool names from **their** server, and gets pass/fail without cloning MCP-Gateway.
- Existing `./scripts/mcp-up.sh` + `tasks/mcp_example.yaml` still work via gateway env / JWT fallback.
- No changes required to evaluators (`contains_substring`, `regex_match`, `tool_sequence`).

### Estimated scope

Small–medium: mainly `mcp_client.py`, `runner.py`, `main.py`, `.env.example`, README; evaluators unchanged.
