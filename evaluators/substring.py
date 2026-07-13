from __future__ import annotations

from models import SuccessCriteria

from .base import BaseEvaluator, EvalResult


class ContainsSubstringEvaluator(BaseEvaluator):
    def evaluate(
        self,
        criteria: SuccessCriteria,
        response: str,
        tool_calls: list[str],
    ) -> EvalResult:
        assert criteria.value is not None, "contains_substring requires `value`"
        passed = criteria.value.lower() in response.lower()
        return EvalResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"substring '{criteria.value}' {'found' if passed else 'not found'}",
        )
