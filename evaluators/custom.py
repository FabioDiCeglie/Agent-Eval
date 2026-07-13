from __future__ import annotations

import importlib

from models import SuccessCriteria

from .base import BaseEvaluator, EvalResult


class CustomFnEvaluator(BaseEvaluator):
    def evaluate(
        self,
        criteria: SuccessCriteria,
        response: str,
        tool_calls: list[str],
    ) -> EvalResult:
        assert criteria.fn is not None, (
            "custom_fn requires `fn` (dotted path, e.g. 'my_module.my_fn')"
        )
        module_path, fn_name = criteria.fn.rsplit(".", 1)
        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)
        result = fn(response=response, tool_calls=tool_calls, criteria=criteria)
        # Accepts either a plain bool or an EvalResult
        if isinstance(result, bool):
            return EvalResult(passed=result, score=1.0 if result else 0.0)
        return result
