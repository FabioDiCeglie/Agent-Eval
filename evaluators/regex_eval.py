from __future__ import annotations

import re

from models import SuccessCriteria

from .base import BaseEvaluator, EvalResult


class RegexMatchEvaluator(BaseEvaluator):
    def evaluate(
        self,
        criteria: SuccessCriteria,
        response: str,
        tool_calls: list[str],
    ) -> EvalResult:
        assert criteria.value is not None, "regex_match requires `value`"
        match = re.search(criteria.value, response, re.IGNORECASE | re.DOTALL)
        passed = match is not None
        return EvalResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"pattern '{criteria.value}' "
            f"{'matched' if passed else 'did not match'}",
        )
