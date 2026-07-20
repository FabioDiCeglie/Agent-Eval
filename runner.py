from __future__ import annotations

import time
from typing import TYPE_CHECKING

import anthropic

from evaluators import evaluate
from mcp_tools import MCPToolService
from models import Task, TaskResult

if TYPE_CHECKING:
    from mcp_client import MCPClient

DEFAULT_MODEL = "claude-opus-4-5"
DEFAULT_MAX_TURNS = 10
DEFAULT_MAX_TOKENS = 4096


class TaskRunner:
    """
    Runs a single Task against Claude, manages the tool-use turn loop,
    collects metrics, and returns a TaskResult.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_turns: int = DEFAULT_MAX_TURNS,
        mcp_client: MCPClient | None = None,
        tool_service: MCPToolService | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic()
        self.model = model
        self.max_turns = max_turns
        self.mcp_client = mcp_client
        self.tool_service = tool_service or MCPToolService()

    async def run(self, task: Task) -> TaskResult:
        start = time.perf_counter()

        messages: list[dict] = [{"role": "user", "content": task.prompt}]
        turn_count = 0
        tool_call_count = 0
        tool_calls_by_name: dict[str, int] = {}
        tool_calls_ordered: list[str] = []
        input_tokens = 0
        output_tokens = 0
        final_response = ""
        tools = (
            self.tool_service.definitions_for(task.tools_allowed)
            if task.tools_allowed
            else []
        )

        try:
            while turn_count < self.max_turns:
                turn_count += 1

                request_kwargs: dict = {
                    "model": self.model,
                    "max_tokens": DEFAULT_MAX_TOKENS,
                    "messages": messages,
                }
                if tools:
                    request_kwargs["tools"] = tools

                response = await self._client.messages.create(**request_kwargs)

                input_tokens += response.usage.input_tokens
                output_tokens += response.usage.output_tokens

                # Collect any text from this turn
                text_blocks = [
                    b.text for b in response.content if b.type == "text"
                ]
                if text_blocks:
                    final_response = "\n".join(text_blocks)

                # Agent is done
                if response.stop_reason == "end_turn":
                    break

                # Claude wants to call tools
                if response.stop_reason == "tool_use":
                    tool_use_blocks = [
                        b for b in response.content if b.type == "tool_use"
                    ]

                    # Append Claude's response to the conversation
                    messages.append({"role": "assistant", "content": response.content})

                    # Execute each tool call and collect results
                    tool_results = []
                    for block in tool_use_blocks:
                        tool_call_count += 1
                        tool_calls_ordered.append(block.name)
                        tool_calls_by_name[block.name] = (
                            tool_calls_by_name.get(block.name, 0) + 1
                        )

                        result_content = await self._call_tool(
                            block.name, block.input
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_content,
                            }
                        )

                    messages.append({"role": "user", "content": tool_results})
                    continue

                # Unexpected stop reason — treat as done
                break

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return TaskResult(
                task_id=task.id,
                task_name=task.name,
                passed=False,
                score=0.0,
                reason=f"runner error: {exc}",
                turn_count=turn_count,
                tool_call_count=tool_call_count,
                tool_calls_by_name=tool_calls_by_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_total_ms=latency_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

        latency_ms = (time.perf_counter() - start) * 1000
        eval_result = evaluate(
            task.success_criteria,
            response=final_response,
            tool_calls=tool_calls_ordered,
        )

        return TaskResult(
            task_id=task.id,
            task_name=task.name,
            passed=eval_result.passed,
            score=eval_result.score,
            reason=eval_result.reason,
            turn_count=turn_count,
            tool_call_count=tool_call_count,
            tool_calls_by_name=tool_calls_by_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_total_ms=latency_ms,
        )

    async def _call_tool(self, name: str, inputs: dict) -> str:
        """Forward a tool call to the MCP server (if available)."""
        if self.mcp_client is None:
            return f"[no mcp_client configured — tool '{name}' not executed]"
        result = await self.mcp_client.call_tool(name, inputs)
        if result.get("is_error"):
            return f"Error: {result['content']}"
        return result["content"]
