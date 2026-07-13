from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from models import SuccessCriteria


@dataclass
class EvalResult:
    passed: bool
    score: float  # 0.0–1.0; binary criteria use 0.0 or 1.0
    reason: str = ""


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(
        self,
        criteria: SuccessCriteria,
        response: str,
        tool_calls: list[str],
    ) -> EvalResult: ...
