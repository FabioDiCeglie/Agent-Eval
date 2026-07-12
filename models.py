from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class CriteriaType(StrEnum):
    contains_substring = "contains_substring"
    regex_match = "regex_match"
    tool_sequence = "tool_sequence"
    llm_judge = "llm_judge"
    custom_fn = "custom_fn"


# How do we know if a task passed?
# SuccessCriteria defines one of 5 strategies:
#   - contains_substring: final response must contain `value`
#   - regex_match:        final response must match `value` as a regex
#   - tool_sequence:      tool calls must appear in the order listed in `sequence`
#   - llm_judge:   a secondary Claude call grades the response against `rubric`;
#                  passes if score >= `passing_score`
#   - custom_fn:   a Python callable at the dotted path in `fn` is imported and called
# Each strategy only uses the fields relevant to it — the others stay None.
class SuccessCriteria(BaseModel):
    type: CriteriaType
    value: str | None = None
    rubric: str | None = None
    passing_score: float = 0.7
    sequence: list[str] = []
    fn: str | None = None


# One evaluation case: what to ask Claude, which tools it can use,
# and what counts as a passing answer.
class Task(BaseModel):
    id: str
    name: str
    prompt: str
    tools_allowed: list[str] = []
    success_criteria: SuccessCriteria
    tags: list[str] = []
