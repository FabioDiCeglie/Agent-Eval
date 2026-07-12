# agent-eval — Architecture Plan

> A CI/CD-style evaluation framework for AI agents using Claude.

---

## 1. Task / Test Case Definition (YAML Format)

Each evaluation task is declared in a YAML file. Tasks are grouped into **suites** (collections of related test cases). The schema is intentionally minimal but expressive enough to cover tool-heavy, multi-turn, and constraint-bound scenarios.

### Single Task Schema

```yaml
# tasks/web_search_suite.yaml

suite: web_search
version: "1.0"
description: "Evaluates the agent's ability to retrieve and synthesise web information."

defaults:
  model: claude-opus-4-5
  max_turns: 10
  timeout_seconds: 60
  budget_tokens: 4000

tasks:
  - id: ws_001
    name: "Simple factual lookup"
    prompt: "What is the population of Tokyo as of 2024?"
    tools_allowed:
      - web_search
    expected_tool_calls:
      - tool: web_search
        min_calls: 1
        max_calls: 3
    success_criteria:
      type: contains_substring
      value: "13"           # answer must reference ~13 M
    tags: [factual, single-turn]

  - id: ws_002
    name: "Multi-source comparison"
    prompt: "Compare the GDP of France and Germany using recent data."
    tools_allowed:
      - web_search
      - calculator
    expected_tool_calls:
      - tool: web_search
        min_calls: 2
    success_criteria:
      type: llm_judge          # uses a secondary Claude call to grade
      rubric: |
        The answer must cite GDP figures for both countries,
        compare them numerically, and state a source year.
      passing_score: 0.7
    tags: [comparison, multi-turn]
    baseline_task_id: ws_002_v0   # reference for regression diff
```

### Success Criteria Types

| Type | Description |
|---|---|
| `contains_substring` | Final response contains a required string |
| `regex_match` | Final response matches a regex pattern |
| `tool_sequence` | Tool calls appear in a specified order |
| `llm_judge` | A grading prompt is sent to Claude with a rubric; score ≥ threshold passes |
| `custom_fn` | A Python callable in `evaluators/` is imported and called |

### Directory Convention

```
tasks/
  ├── suites/
  │   ├── web_search_suite.yaml
  │   ├── code_generation_suite.yaml
  │   └── mcp_tool_suite.yaml
  └── fixtures/           # static files / mock responses referenced by tasks
      └── sample_code.py
```

---

## 2. Agent Invocation & Observation via Claude API

### Invocation Model

Agents are invoked via the **Anthropic Python SDK** using the Messages API with tool use enabled. Each task run follows this lifecycle:

```
TaskRunner
  ├── Build system prompt + user message from task YAML
  ├── Inject tool definitions (declared in task YAML, resolved against gateway)
  ├── Open a Run context (captures all events)
  │   └── Loop: send message → receive response → forward tool calls to MCP Gateway → repeat
  │         until stop_reason == "end_turn" or max_turns exceeded
  └── Emit RunResult to the collector
```

### Turn Loop (Pseudo-flow)

```
1. POST /v1/messages  { model, system, messages, tools, max_tokens }
2. If stop_reason == "tool_use":
     a. Extract tool_use blocks → log each call (name, input, timestamp)
     b. POST tool call to MCP Gateway  →  receive tool_result
     c. Append tool_result blocks to messages
     d. Goto 1
3. If stop_reason == "end_turn":
     a. Extract final text response
     b. Run success_criteria evaluation
     c. Close Run and return RunResult
```

### Observation Hooks

The runner wraps every API call with an **ObservationMiddleware** that records:

- Raw request/response payloads (stored as JSONL per run)
- Per-turn token usage (`input_tokens`, `output_tokens`, `cache_read_input_tokens`)
- Wall-clock latency for each API call
- Tool call metadata: tool name, input size, output size, latency

This follows an **OpenTelemetry-inspired spans model** — each turn is a span, each tool call is a child span.

---

## 3. Metrics Captured

### Per-Run Metrics

| Metric | Description | How Captured |
|---|---|---|
| `task_completed` | Boolean — did the agent satisfy `success_criteria`? | Evaluator result |
| `tool_call_count` | Total number of tool invocations across all turns | ObservationMiddleware |
| `tool_calls_by_name` | Dict of `{tool_name: count}` | ObservationMiddleware |
| `turn_count` | Number of full message roundtrips | ObservationMiddleware |
| `latency_total_ms` | End-to-end wall time for the full run | `time.perf_counter` |
| `latency_per_turn_ms` | List of per-turn latencies | ObservationMiddleware |
| `input_tokens` | Total input tokens (all turns summed) | API usage field |
| `output_tokens` | Total output tokens (all turns summed) | API usage field |
| `cost_usd` | Estimated cost using model pricing table | `pricing/model_prices.yaml` |
| `success_score` | Float 0–1 for `llm_judge` tasks; 0 or 1 for binary tasks | Evaluator |
| `error` | Exception class and message if run crashed | Exception handler |

### Suite-Level Metrics (aggregated)

| Metric | Description |
|---|---|
| `pass_rate` | `tasks_passed / tasks_run` |
| `avg_cost_usd` | Mean cost across all runs in the suite |
| `avg_latency_ms` | Mean end-to-end latency |
| `avg_tool_calls` | Mean tool calls per task |
| `p95_latency_ms` | 95th percentile latency |

### Regression vs Baseline

Each run can be compared against a **baseline result set** (stored as a JSON snapshot):

- `regression_delta`: for numeric metrics, the signed change vs baseline
- `regression_flag`: if `pass_rate` drops by more than a configurable threshold (default: 5%), flag as regression
- `new_failures`: task IDs that passed in baseline but failed in current run
- `new_passes`: task IDs that failed in baseline but now pass (improvements)

The baseline is pinned by a `baseline_run_id` or a git commit SHA and stored in `results/baselines/`.

---

## 4. Output Format

### 4a. CLI Report

Printed to stdout at the end of every run via `rich` tables.

```
╔══════════════════════════════════════════════════════╗
║           agent-eval  ·  Run abc123  ·  claude-opus  ║
╠══════════════════════════════════════════════════════╣
║  Suite: web_search   Tasks: 8   Duration: 42.3s       ║
╠══════════════════════════════════════════════════════╣
║  ID       Name                  Pass  Turns  Cost     ║
║  ───────  ────────────────────  ────  ─────  ──────── ║
║  ws_001   Simple factual lookup  ✓     2     $0.0031  ║
║  ws_002   Multi-source compare   ✓     4     $0.0089  ║
║  ws_003   Ambiguous query        ✗     8     $0.0210  ║
╠══════════════════════════════════════════════════════╣
║  Pass Rate: 87.5%   Avg Cost: $0.0083   ▲ vs baseline ║
╚══════════════════════════════════════════════════════╝
```

Flags:
- `--verbose` prints full traces per task
- `--diff baseline_run_id` shows regression delta column
- `--fail-fast` stops on first failure

### 4b. JSON Results

Every run writes a structured JSON file to `results/runs/<run_id>.json`:

```json
{
  "run_id": "abc123",
  "timestamp": "2026-07-12T09:00:00Z",
  "model": "claude-opus-4-5",
  "suite": "web_search",
  "baseline_run_id": "xyz789",
  "summary": {
    "tasks_run": 8,
    "tasks_passed": 7,
    "pass_rate": 0.875,
    "avg_cost_usd": 0.0083,
    "avg_latency_ms": 5287,
    "avg_tool_calls": 2.4,
    "p95_latency_ms": 9100,
    "regression_flag": false,
    "new_failures": [],
    "new_passes": ["ws_007"]
  },
  "tasks": [
    {
      "task_id": "ws_001",
      "passed": true,
      "success_score": 1.0,
      "turn_count": 2,
      "tool_call_count": 1,
      "tool_calls_by_name": { "web_search": 1 },
      "input_tokens": 843,
      "output_tokens": 312,
      "cost_usd": 0.0031,
      "latency_total_ms": 3210,
      "error": null
    }
  ],
  "raw_traces": "results/traces/abc123/"
}
```

Raw turn-by-turn traces are stored as JSONL in `results/traces/<run_id>/<task_id>.jsonl`.

### 4c. Leaderboard-Style Summary

A persistent `results/leaderboard.json` is updated after each run. It ranks model/config combinations by composite score.

```json
{
  "last_updated": "2026-07-12T09:00:00Z",
  "suite": "web_search",
  "entries": [
    {
      "rank": 1,
      "model": "claude-opus-4-5",
      "run_id": "abc123",
      "pass_rate": 0.875,
      "avg_cost_usd": 0.0083,
      "avg_latency_ms": 5287,
      "composite_score": 0.81,
      "date": "2026-07-12"
    },
    {
      "rank": 2,
      "model": "claude-sonnet-4-5",
      "run_id": "def456",
      "pass_rate": 0.750,
      "avg_cost_usd": 0.0021,
      "avg_latency_ms": 3100,
      "composite_score": 0.74,
      "date": "2026-07-10"
    }
  ]
}
```

The `composite_score` formula is configurable in `config/scoring.yaml` (default: weighted average of pass rate, inverse cost rank, and inverse latency rank).

A static HTML leaderboard can be generated with `agent-eval report --html`.

---

## 5. MCP Gateway Integration

### What the Gateway Already Does

The [MCP Gateway](https://github.com/FabioDiCeglie/MCP-Gateway) is a fully built control plane that handles everything between agents and tools:

- **Auth** — JWT HS256 per client identity
- **Rate limiting** — Redis fixed-window per client (10 `tools/call` / 60s)
- **Tool policy** — allow-list enforcement via `policy.yaml`
- **Audit log** — append-only tool call log (SQLite / Postgres)
- **Tracing** — OpenTelemetry → Jaeger

agent-eval does **not** reimplement any of this. It treats the gateway as a black-box HTTP endpoint.

### High-Level System View

```
┌─────────────────────────────────────────────────────────┐
│                      agent-eval                         │
│                                                         │
│   YAML Suites → SuiteRunner → TaskRunner → Evaluators  │
│                                   │              │      │
│                                   │              ▼      │
│                                   │           Reports   │
└───────────────────────────────────┼─────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            Anthropic API                 ┌──────────────────┐
           (Claude Models)                │   MCP Gateway    │
                                          │  (separate repo) │
                                          │                  │
                                          │  auth · limits   │
                                          │  policy · audit  │
                                          │  tracing         │
                                          └────────┬─────────┘
                                                   │
                                                   ▼
                                            MCP Servers
                                         (web_search, etc.)
```

MCP Gateway behaves like any other microservice from agent-eval's perspective:

```
agent-eval  ──POST /mcp──►  MCP Gateway  :8080
            ◄──JSON result──
```

agent-eval only needs `MCP_GATEWAY_URL` and `MCP_GATEWAY_TOKEN` in its `.env`. Everything inside the gateway box (Redis, Postgres, Jaeger, policy engine) is fully encapsulated. In CI, the gateway runs as a Docker sidecar and the two services communicate over localhost.

### What agent-eval Does (and Only This)

```
agent-eval's scope:
  define tasks  →  invoke Claude  →  measure outcomes  →  report results
```

Tool calls flow through the gateway transparently. agent-eval is only responsible for:
1. Telling Claude which tools are available (from the task YAML)
2. Forwarding tool call requests to the gateway and returning responses to Claude
3. Recording the tool name, call count, and latency **from agent-eval's perspective** (i.e., the round-trip time it observes, not internal gateway metrics)

### Architecture

```
Claude API
    ↑↓  (Messages API — tool_use / tool_result blocks)
TaskRunner  (agent-eval)
    │
    │  POST /mcp  { tool_name, input }
    ▼
MCP Gateway  :8080        ← auth, rate-limit, policy, audit, tracing all live here
    │
    ▼
Upstream MCP Server(s)    ← actual tool execution
```

### Minimal MCP Client

agent-eval only needs a thin `MCPClient` — a single `async def call_tool(name, input) -> dict` that:

1. POSTs to `{GATEWAY_URL}/mcp` with the tool call payload
2. Attaches the JWT from `MCP_GATEWAY_TOKEN` env var
3. Returns the tool result JSON
4. Records wall-clock latency for the metric `mcp_roundtrip_ms`

No interceptor, no proxy, no mock mode in agent-eval itself. If offline/deterministic runs are needed, point `GATEWAY_URL` at a locally running gateway instance configured with its own mock upstream.

### Configuration

```yaml
# config/mcp_config.yaml
gateway_url: "http://localhost:8080"   # set via MCP_GATEWAY_URL env var in CI
```

That's the entire MCP configuration surface for agent-eval.

### What agent-eval Measures from MCP Calls

| Metric | Source |
|---|---|
| `tool_call_count` | Count of tool_use blocks emitted by Claude |
| `tool_calls_by_name` | `{tool_name: count}` dict |
| `mcp_roundtrip_ms` | agent-eval's observed latency per tool call |

Deeper metrics (policy hits, rate-limit events, upstream latency, full audit trail) are already captured by the gateway — query them via the gateway's audit log or Jaeger UI, not from agent-eval.

---

## 6. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.11+ | Native Anthropic SDK, rich ecosystem for testing & ML tooling |
| **Claude SDK** | `anthropic` (official Python SDK) | Streaming, tool use, vision, prompt caching |
| **CLI** | `click` | Ergonomic command building with subcommands |
| **CLI Rendering** | `rich` | Beautiful tables, progress bars, diff rendering in terminal |
| **YAML parsing** | `pyyaml` + `pydantic` | YAML load → Pydantic model validation → type-safe task objects |
| **Data / results** | `json` (stdlib) + `pandas` (optional, for leaderboard aggregation) | Lightweight; pandas only for summary analytics |
| **HTTP (MCP client)** | `httpx` | Async-capable, SSE support for MCP streaming |
| **Async runtime** | `asyncio` (stdlib) | Needed for parallel task execution and streaming API calls |
| **Testing** | `pytest` + `pytest-asyncio` | Framework self-tests and evaluator unit tests |
| **Pricing table** | YAML file in `pricing/` | Easy to update; no external dependency |
| **HTML report** | `jinja2` | Templated leaderboard HTML generation |
| **Env / secrets** | `python-dotenv` | `.env` file for `ANTHROPIC_API_KEY`, MCP gateway URL |
| **Packaging** | `pyproject.toml` (PEP 517) | Modern Python packaging; exposes `agent-eval` CLI entry point |

---

## 7. Folder Structure

```
agent-eval/
│
├── Plan.md                        ← this document
├── README.md
├── pyproject.toml                 ← package metadata, dependencies, CLI entry point
├── .env.example                   ← ANTHROPIC_API_KEY, MCP_GATEWAY_URL, etc.
├── .gitignore
│
├── agent_eval/                    ← main Python package
│   ├── __init__.py
│   │
│   ├── cli/                       ← Click CLI entry points
│   │   ├── __init__.py
│   │   ├── main.py                ← `agent-eval` root command
│   │   ├── run.py                 ← `agent-eval run <suite>`
│   │   ├── report.py              ← `agent-eval report [--html] [--diff]`
│   │   └── baseline.py            ← `agent-eval baseline set <run_id>`
│   │
│   ├── core/                      ← domain models and orchestration
│   │   ├── __init__.py
│   │   ├── models.py              ← Pydantic models: Task, Suite, RunResult, TaskResult
│   │   ├── runner.py              ← TaskRunner: invokes Claude, manages turn loop
│   │   ├── suite_runner.py        ← SuiteRunner: runs all tasks, parallel option
│   │   └── observation.py         ← ObservationMiddleware: metrics collection
│   │
│   ├── evaluators/                ← success criteria implementations
│   │   ├── __init__.py
│   │   ├── base.py                ← AbstractEvaluator interface
│   │   ├── substring.py           ← contains_substring
│   │   ├── regex_eval.py          ← regex_match
│   │   ├── tool_sequence.py       ← tool_sequence order check
│   │   ├── llm_judge.py           ← LLM-as-judge via Claude API
│   │   └── custom.py              ← dynamic import for custom_fn tasks
│   │
│   ├── tools/                     ← MCP Gateway client (thin HTTP wrapper only)
│   │   ├── __init__.py
│   │   └── mcp_client.py          ← MCPClient: call_tool() → POST /mcp to gateway
│   │
│   ├── reporting/                 ← output formatting
│   │   ├── __init__.py
│   │   ├── cli_report.py          ← rich table renderer for terminal
│   │   ├── json_writer.py         ← writes results/runs/<run_id>.json
│   │   ├── leaderboard.py         ← reads/writes results/leaderboard.json
│   │   └── html_report.py         ← jinja2 HTML generation
│   │
│   ├── regression/                ← baseline comparison logic
│   │   ├── __init__.py
│   │   └── comparator.py          ← diffs current RunResult vs baseline
│   │
│   └── pricing/                   ← cost estimation
│       ├── __init__.py
│       └── calculator.py          ← reads model_prices.yaml, computes cost_usd
│
├── tasks/                         ← evaluation task definitions (user-owned)
│   └── suites/
│       ├── web_search_suite.yaml
│       ├── code_generation_suite.yaml
│       └── mcp_tool_suite.yaml
│
├── config/                        ← framework configuration
│   ├── mcp_config.yaml            ← gateway_url only (one line)
│   ├── scoring.yaml               ← composite_score formula weights
│   └── defaults.yaml              ← global defaults (model, timeouts, etc.)
│
├── pricing/
│   └── model_prices.yaml          ← per-model input/output token prices
│
├── results/                       ← generated at runtime (git-ignored except baselines)
│   ├── runs/                      ← <run_id>.json per run
│   ├── traces/                    ← <run_id>/<task_id>.jsonl raw turn traces
│   ├── leaderboard.json
│   └── baselines/                 ← pinned baseline snapshots (committed to git)
│       └── baseline_abc123.json
│
├── templates/                     ← jinja2 HTML templates
│   └── leaderboard.html.j2
│
└── tests/                         ← framework's own test suite
    ├── unit/
    │   ├── test_models.py
    │   ├── test_evaluators.py
    │   └── test_pricing.py
    └── integration/
        ├── test_runner.py          ← runs a minimal task against Claude (needs API key)
        └── test_mcp_client.py      ← calls a live MCP Gateway instance (needs gateway running)
```

---

## 8. Key Design Decisions

### Async-first runner
All Claude API calls are async (`anthropic.AsyncAnthropic`). The `SuiteRunner` runs tasks concurrently with a configurable `max_concurrency` limit (default: 3) to avoid rate limits while keeping wall time low.

### LLM-as-judge is a first-class evaluator
For open-ended tasks, the `llm_judge` evaluator sends a structured grading prompt to a separate Claude call (typically `claude-haiku` for cost efficiency). The rubric, model, and passing score are defined per task in YAML.

### Baseline snapshots are committed to git
`results/baselines/` is the only subdirectory of `results/` that is committed. This makes regression diffs part of the code review process: a PR that degrades the pass rate will show a changed baseline file.

### MCP Gateway is a dependency, not a sub-component
agent-eval delegates all tool routing, auth, rate limiting, policy, and audit to the [MCP Gateway](https://github.com/FabioDiCeglie/MCP-Gateway). The only integration surface is `GATEWAY_URL` + `MCP_GATEWAY_TOKEN`. In CI, the gateway runs as a Docker service (using its own `docker-compose.yaml`); agent-eval just points at it. There is no mock layer inside agent-eval.

### Pricing is a YAML file, not hardcoded
`pricing/model_prices.yaml` is updated independently of the framework code. A CI step can auto-update it from the Anthropic pricing page.

### Composable CLI
```
agent-eval run   web_search_suite.yaml --model claude-sonnet-4-5 --diff latest
agent-eval report --html --open
agent-eval baseline set abc123
agent-eval baseline list
```

---

## 9. CI/CD Integration Example

```yaml
# .github/workflows/agent-eval.yml
name: Agent Eval

on:
  push:
    branches: [main]
  pull_request:

jobs:
  eval:
    runs-on: ubuntu-latest

    services:
      # Spin up MCP Gateway (from FabioDiCeglie/MCP-Gateway) as a sidecar
      mcp-gateway:
        image: ghcr.io/fabiodiceglie/mcp-gateway:latest
        ports: ["8080:8080"]
        env:
          GATEWAY_JWT_SECRET: ${{ secrets.MCP_GATEWAY_JWT_SECRET }}
          GATEWAY_REDIS_URL: redis://redis:6379/0
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: agent-eval run tasks/suites/web_search_suite.yaml --diff latest --fail-on-regression
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          MCP_GATEWAY_URL: http://localhost:8080
          MCP_GATEWAY_TOKEN: ${{ secrets.MCP_GATEWAY_TOKEN }}
      - uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: results/runs/
```

---

*Plan version 1.1 — simplified MCP integration; gateway treated as external dependency.*
