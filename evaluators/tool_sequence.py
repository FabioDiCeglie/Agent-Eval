from __future__ import annotations

from models import SuccessCriteria

from .base import BaseEvaluator, EvalResult


class ToolSequenceEvaluator(BaseEvaluator):
    def evaluate(
        self,
        criteria: SuccessCriteria,
        response: str,
        tool_calls: list[str],
    ) -> EvalResult:
        expected = criteria.sequence
        if not expected:
            return EvalResult(passed=True, score=1.0, reason="no sequence required")

        # Check expected tools appear as a subsequence in actual call order
        idx = 0
        for call in tool_calls:
            if idx < len(expected) and call == expected[idx]:
                idx += 1
        passed = idx == len(expected)
        return EvalResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=(
                f"sequence matched {idx}/{len(expected)} tools in order"
                if not passed
                else f"tool sequence matched: {expected}"
            ),
        )
