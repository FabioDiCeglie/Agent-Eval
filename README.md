# agent-eval

CI/CD-style evaluation framework for AI agents using Claude.

## Setup

```bash
uv sync --all-groups
cp .env.example .env  # fill in your API keys

# install the git pre-commit hook (one-time)
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

## Usage

```bash
uv run agent-eval --help
```
