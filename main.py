from __future__ import annotations

import asyncio
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.table import Table

from models import Task, TaskResult
from runner import TaskRunner

load_dotenv()

console = Console()


def load_tasks(path: str | Path) -> list[Task]:
    """Read a YAML file and return a validated list of Task objects."""
    raw = yaml.safe_load(Path(path).read_text())
    return [Task.model_validate(t) for t in raw["tasks"]]


def print_results(results: list[TaskResult], model: str) -> None:
    table = Table(
        title=f"agent-eval · {model}",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Pass", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Turns", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Reason", style="dim")

    passed = 0
    for r in results:
        status = "[green]✓[/green]" if r.passed else "[red]✗[/red]"
        if r.passed:
            passed += 1
        table.add_row(
            r.task_id,
            r.task_name,
            status,
            f"{r.score:.2f}",
            str(r.turn_count),
            str(r.input_tokens + r.output_tokens),
            f"{r.latency_total_ms:.0f}ms",
            r.error or r.reason,
        )

    console.print(table)

    total = len(results)
    rate = passed / total * 100 if total else 0
    color = "green" if rate == 100 else "yellow" if rate >= 50 else "red"
    console.print(
        f"[bold]Pass rate:[/bold] [{color}]{passed}/{total} ({rate:.0f}%)[/{color}]"
    )


@click.group()
def cli():
    """agent-eval: CI/CD-style evaluation framework for AI agents."""


@cli.command()
@click.argument("suite", type=click.Path(exists=True))
@click.option("--model", default="claude-haiku-4-5", show_default=True,
              help="Claude model to use.")
@click.option("--max-turns", default=10, show_default=True,
              help="Max turns per task.")
def run(suite: str, model: str, max_turns: int) -> None:
    """Run all tasks in a YAML suite file against Claude."""
    tasks = load_tasks(suite)
    console.print(f"[bold]Loaded {len(tasks)} task(s) from[/bold] {suite}\n")

    runner = TaskRunner(model=model, max_turns=max_turns)
    results: list[TaskResult] = []

    async def run_all() -> None:
        for task in tasks:
            console.print(f"  Running [cyan]{task.id}[/cyan] {task.name}…")
            result = await runner.run(task)
            results.append(result)

    asyncio.run(run_all())

    console.print()
    print_results(results, model)


if __name__ == "__main__":
    cli()
