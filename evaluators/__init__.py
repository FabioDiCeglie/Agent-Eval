from __future__ import annotations

from models import CriteriaType, SuccessCriteria

from .base import BaseEvaluator, EvalResult
from .regex_eval import RegexMatchEvaluator
from .substring import ContainsSubstringEvaluator
from .tool_sequence import ToolSequenceEvaluator

__all__ = [
    "EvalResult",
    "BaseEvaluator",
    "ContainsSubstringEvaluator",
    "RegexMatchEvaluator",
    "ToolSequenceEvaluator",
    "evaluate",
]

_EVALUATORS: dict[CriteriaType, BaseEvaluator] = {
    CriteriaType.contains_substring: ContainsSubstringEvaluator(),
    CriteriaType.regex_match: RegexMatchEvaluator(),
    CriteriaType.tool_sequence: ToolSequenceEvaluator(),
}


def evaluate(
    criteria: SuccessCriteria,
    response: str,
    tool_calls: list[str] | None = None,
) -> EvalResult:
    """Entry point — pick the right evaluator and run it."""
    tool_calls = tool_calls or []
    evaluator = _EVALUATORS[criteria.type]
    return evaluator.evaluate(criteria, response, tool_calls)
