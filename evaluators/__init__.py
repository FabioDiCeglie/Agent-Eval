from __future__ import annotations

import anthropic

from models import CriteriaType, SuccessCriteria

from .base import BaseEvaluator, EvalResult
from .custom import CustomFnEvaluator
from .llm_judge import LLMJudgeEvaluator
from .regex_eval import RegexMatchEvaluator
from .substring import ContainsSubstringEvaluator
from .tool_sequence import ToolSequenceEvaluator

__all__ = [
    "EvalResult",
    "BaseEvaluator",
    "ContainsSubstringEvaluator",
    "RegexMatchEvaluator",
    "ToolSequenceEvaluator",
    "LLMJudgeEvaluator",
    "CustomFnEvaluator",
    "evaluate",
]

_EVALUATORS: dict[CriteriaType, BaseEvaluator] = {
    CriteriaType.contains_substring: ContainsSubstringEvaluator(),
    CriteriaType.regex_match: RegexMatchEvaluator(),
    CriteriaType.tool_sequence: ToolSequenceEvaluator(),
    CriteriaType.custom_fn: CustomFnEvaluator(),
}


def evaluate(
    criteria: SuccessCriteria,
    response: str,
    tool_calls: list[str] | None = None,
    llm_client: anthropic.Anthropic | None = None,
) -> EvalResult:
    """Entry point — pick the right evaluator and run it."""
    tool_calls = tool_calls or []

    if criteria.type == CriteriaType.llm_judge:
        return LLMJudgeEvaluator(llm_client).evaluate(criteria, response, tool_calls)

    evaluator = _EVALUATORS[criteria.type]
    return evaluator.evaluate(criteria, response, tool_calls)
