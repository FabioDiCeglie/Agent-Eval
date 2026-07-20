from __future__ import annotations

from pathlib import Path

from main import load_suite


def test_load_suite_tasks(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
tasks:
  - id: t1
    name: n
    prompt: p
    tools_allowed: []
    success_criteria:
      type: contains_substring
      value: x
"""
    )
    doc = load_suite(path)
    assert len(doc.tasks) == 1
    assert doc.tasks[0].id == "t1"
