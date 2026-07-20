# agent-eval — Plan

A YAML-based test runner for Claude agents. Define tasks, run them, get pass/fail with basic metrics.

---

## What it does

```
YAML task file  →  TaskRunner  →  Claude API  →  Evaluator  →  CLI report
                                      ↓
                               MCP server (Streamable HTTP, if tools_allowed)
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
mcp_client.py    Streamable HTTP MCP client
mcp_tools.py     MCPToolService — discover tools, map to Anthropic defs
evaluators/      contains_substring, regex_match, tool_sequence
tasks/           Example task files
scripts/         mcp-up.sh, mcp-down.sh, pre-commit hook
```

### Turn loop

```
1. POST /v1/messages  { model, messages, tools }
2. If stop_reason == "tool_use":
     a. Forward each tool call to the MCP server (--mcp-url)
     b. Append tool results to messages
     c. Go to 1
3. If stop_reason == "end_turn":
     a. Run success_criteria against final response
     b. Return TaskResult
```

### MCP connection

Tool tasks use **Streamable HTTP** MCP. Pass **`--mcp-url`** on `run` when any task has `tools_allowed`. Optional auth via `MCP_AUTH_TOKEN`, `MCP_HEADERS`, or `GATEWAY_JWT_SECRET` (gateway demo). See [README.md](README.md).

For the local gateway stack: `./scripts/mcp-up.sh`, then `--mcp-url http://localhost:8080`.

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
cp .env.example .env   # ANTHROPIC_API_KEY; MCP auth vars if using tools

uv run agent-eval run tasks/example.yaml
uv run agent-eval run tasks/mcp_example.yaml --mcp-url http://localhost:8080
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
uv run agent-eval run tasks/my_suite.yaml --mcp-url https://mcp.example.com
```

Optional auth in `.env`: `MCP_AUTH_TOKEN`, `MCP_HEADERS`, or `GATEWAY_JWT_SECRET` (local gateway demo).

Text-only suites (`tools_allowed: []`) unchanged — no MCP connection.

### Problems in 1.x

- Tool schemas are hardcoded in `runner.py` (`echo`, `ping`) for the gateway demo server.
- Env and docs center on `MCP_GATEWAY_URL` + `GATEWAY_JWT_SECRET`.
- Per-task `tools_allowed` must stay in sync with gateway `policy.yaml` with no discovery.
- Other developers cannot plug in their own MCP without forking or editing Python.

### Work items (2.0 rollout)

| # | Item | Status |
|---|------|--------|
| 1 | Auth: `MCP_AUTH_TOKEN`, `MCP_HEADERS`; JWT from `GATEWAY_JWT_SECRET` when token unset | **Done** |
| 2 | URL: `--mcp-url` only (no env/YAML URL); normalize `…/mcp` | **Done** |
| 3 | CLI `--mcp-url` required for tool suites | **Done** |
| 4 | `list_tools()` at suite start; `MCPToolService`; remove `_TOOL_DEFS` | **Done** |
| 5 | README + Plan docs (generic MCP default; gateway appendix) | **Done** |

**Delivered behavior (summary):**

1. **Connection** — `--mcp-url` on `run` when any task uses tools. Auth via env only.
2. **Tool discovery** — `list_tools()` → Anthropic definitions; `tools_allowed` filters per task.
3. **No hardcoded demo schemas** in `runner.py`.
4. **Docs** — README leads with any MCP server; gateway under appendix.

**Deferred / out of scope:**

- Suite-level `mcp.url` in YAML (CLI-only URL by design)
- `MCP_URL` / `MCP_GATEWAY_URL` env vars for endpoint

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
     a. Forward each tool call to MCP (--mcp-url)
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

- [x] Developer sets `ANTHROPIC_API_KEY`, passes `--mcp-url` to **their** Streamable HTTP MCP, uses tool names from `list_tools()` in YAML — pass/fail without cloning MCP-Gateway.
- [x] `./scripts/mcp-up.sh` + `tasks/mcp_example.yaml --mcp-url http://localhost:8080` + `GATEWAY_JWT_SECRET` still works.
- [x] Evaluators unchanged (`contains_substring`, `regex_match`, `tool_sequence`).

### Estimated scope

Small–medium: mainly `mcp_client.py`, `runner.py`, `main.py`, `.env.example`, README; evaluators unchanged.
