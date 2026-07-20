from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from main import cli


def test_run_tool_suite_without_mcp_url_fails(tmp_path: Path) -> None:
    suite = tmp_path / "tools.yaml"
    suite.write_text(
        """
tasks:
  - id: t1
    name: n
    prompt: use echo
    tools_allowed: [echo]
    success_criteria:
      type: contains_substring
      value: ok
"""
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["run", str(suite)])
    assert result.exit_code != 0
    assert "--mcp-url" in result.output
