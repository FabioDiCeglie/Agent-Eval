from __future__ import annotations

import asyncio
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.table import Table

from mcp_client import MCPClient, strip_mcp_url
from models import SuiteDocument, Task, TaskResult
from runner import DEFAULT_MAX_TURNS, TaskRunner

load_dotenv()

console = Console()


def load_suite(path: str | Path) -> SuiteDocument:
    """Read a YAML suite file and return validated tasks and optional MCP config."""
    raw = yaml.safe_load(Path(path).read_text())
    return SuiteDocument.model_validate(raw)


def load_tasks(path: str | Path) -> list[Task]:
    """Read a YAML file and return a validated list of Task objects."""
    return load_suite(path).tasks


def print_results(results: list[TaskResult], model: str) -> None:
    table = Table(
        title=f"agent-eval · {model}",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Pass", justify="center")
    table.add_column("Turns", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Reason", style="dim")

    for result in results:
        status = "[green]✓[/green]" if result.passed else "[red]✗[/red]"
        table.add_row(
            result.task_id,
            result.task_name,
            status,
            str(result.turn_count),
            str(result.input_tokens + result.output_tokens),
            f"{result.latency_total_ms:.0f}ms",
            result.error or result.reason,
        )

    console.print(table)

    passed = sum(result.passed for result in results)
    total = len(results)
    rate = passed / total * 100 if total else 0
    color = "green" if rate == 100 else "yellow" if rate >= 50 else "red"
    console.print(
        f"[bold]Pass rate:[/bold] [{color}]{passed}/{total} ({rate:.0f}%)[/{color}]"
    )


async def run_suite(
    tasks: list[Task],
    model: str,
    max_turns: int,
    *,
    mcp_url: str | None = None,
) -> list[TaskResult]:
    needs_mcp = any(task.tools_allowed for task in tasks)
    mcp_client = MCPClient(mcp_url=mcp_url) if needs_mcp else None
    runner = TaskRunner(model=model, max_turns=max_turns, mcp_client=mcp_client)

    try:
        results: list[TaskResult] = []
        for task in tasks:
            console.print(f"  Running [cyan]{task.id}[/cyan] {task.name}…")
            results.append(await runner.run(task))
        return results
    finally:
        if mcp_client is not None:
            await mcp_client.close()


@click.group()
def cli():
    """agent-eval: CI/CD-style evaluation framework for AI agents."""


@cli.command()
@click.argument("suite", type=click.Path(exists=True))
@click.option(
    "--model",
    default="claude-haiku-4-5",
    show_default=True,
    help="Claude model to use.",
)
@click.option(
    "--max-turns",
    default=DEFAULT_MAX_TURNS,
    show_default=True,
    help="Max turns per task.",
)
@click.option(
    "--mcp-url",
    default=None,
    help="MCP server URL (required when the suite uses tools).",
)
def run(suite: str, model: str, max_turns: int, mcp_url: str | None) -> None:
    """Run all tasks in a YAML suite file against Claude."""
    doc = load_suite(suite)
    tasks = doc.tasks
    resolved_mcp = strip_mcp_url(mcp_url)
    if any(task.tools_allowed for task in tasks) and not resolved_mcp:
        raise click.ClickException(
            "This suite uses tools. Pass --mcp-url (e.g. http://localhost:8080)."
        )
    console.print(f"[bold]Loaded {len(tasks)} task(s) from[/bold] {suite}\n")

    results = asyncio.run(
        run_suite(tasks, model, max_turns, mcp_url=resolved_mcp)
    )

    console.print()
    print_results(results, model)


if __name__ == "__main__":
    cli()
