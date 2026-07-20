from __future__ import annotations

import pytest
from mcp.types import Tool

from mcp_tools import MCPToolService
from models import SuccessCriteria, Task


def test_to_anthropic_mapping() -> None:
    tool = Tool(
        name="echo",
        description="Echo back",
        inputSchema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    )
    service = MCPToolService.from_mcp_tools([tool])
    assert service.definitions_for(["echo"]) == [
        {
            "name": "echo",
            "description": "Echo back",
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        }
    ]


def test_definitions_for_filters_catalog() -> None:
    service = MCPToolService.from_mcp_tools(
        [
            Tool(name="echo", inputSchema={"type": "object", "properties": {}}),
            Tool(name="ping", inputSchema={"type": "object", "properties": {}}),
        ]
    )
    tools = service.definitions_for(["echo"])
    assert [t["name"] for t in tools] == ["echo"]


def test_validate_tasks_raises_for_unknown() -> None:
    service = MCPToolService.from_mcp_tools(
        [Tool(name="echo", inputSchema={"type": "object", "properties": {}})]
    )
    tasks = [
        Task(
            id="t1",
            name="n",
            prompt="p",
            tools_allowed=["missing"],
            success_criteria=SuccessCriteria(type="contains_substring", value="x"),
        )
    ]
    with pytest.raises(ValueError, match="missing"):
        service.validate_tasks(tasks)
