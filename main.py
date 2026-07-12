import click


@click.group()
def cli():
    """agent-eval: CI/CD-style evaluation framework for AI agents."""


@cli.command()
def hello():
    """Smoke test — prints a greeting."""
    click.echo("B")


if __name__ == "__main__":
    cli()
