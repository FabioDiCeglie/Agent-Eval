from __future__ import annotations

import json
import re

import anthropic

from models import SuccessCriteria

from .base import BaseEvaluator, EvalResult


class LLMJudgeEvaluator(BaseEvaluator):
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client or anthropic.Anthropic()

    def evaluate(
        self,
        criteria: SuccessCriteria,
        response: str,
        tool_calls: list[str],
    ) -> EvalResult:
        assert criteria.rubric is not None, "llm_judge requires `rubric`"

        prompt = (
            "You are a strict grader. Score the following agent response"
            " against the rubric.\n\n"
            f"<rubric>\n{criteria.rubric}\n</rubric>\n\n"
            f"<response>\n{response}\n</response>\n\n"
            "Reply with a JSON object: "
            '{"score": <float 0.0-1.0>, "reason": "<one sentence>"}'
        )

        message = self._client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            return EvalResult(
                passed=False,
                score=0.0,
                reason=f"judge returned unparseable output: {raw[:100]}",
            )

        data = json.loads(json_match.group())
        score = float(data.get("score", 0.0))
        reason = data.get("reason", "")
        passed = score >= criteria.passing_score
        return EvalResult(passed=passed, score=score, reason=reason)
