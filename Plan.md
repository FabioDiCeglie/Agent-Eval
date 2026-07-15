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
