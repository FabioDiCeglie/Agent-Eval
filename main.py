from __future__ import annotations

from pathlib import Path

import click
import yaml

from models import Task


def load_tasks(path: str | Path) -> list[Task]:
    """Read a YAML file and return a validated list of Task objects."""
    raw = yaml.safe_load(Path(path).read_text())
    return [Task.model_validate(t) for t in raw["tasks"]]


@click.group()
def cli():
    """agent-eval: CI/CD-style evaluation framework for AI agents."""


@cli.command()
@click.argument("suite", type=click.Path(exists=True))
def run(suite: str):
    """Load and display tasks from a YAML suite file."""
    tasks = load_tasks(suite)
    for task in tasks:
        click.echo(f"[{task.id}] {task.name} — {task.success_criteria.type}")


if __name__ == "__main__":
    cli()
