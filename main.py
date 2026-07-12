import click


@click.group()
def cli():
    """agent-eval: CI/CD-style evaluation framework for AI agents."""


if __name__ == "__main__":
    cli()
