from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import Tool

from models import Task

if TYPE_CHECKING:
    from mcp_client import MCPClient

AnthropicToolDef = dict[str, Any]


class MCPToolService:
    """Discover MCP tools and expose Anthropic tool definitions per task."""

    def __init__(self, catalog: dict[str, AnthropicToolDef] | None = None) -> None:
        self._catalog = dict(catalog) if catalog else {}

    @classmethod
    def from_mcp_tools(cls, tools: list[Tool]) -> MCPToolService:
        return cls({tool.name: cls._to_anthropic(tool) for tool in tools})

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._catalog)

    async def load(self, client: MCPClient) -> None:
        """Refresh catalog from the connected MCP server."""
        tools = await client.list_tools()
        self._catalog = {tool.name: self._to_anthropic(tool) for tool in tools}

    def validate_tasks(self, tasks: list[Task]) -> None:
        missing: set[str] = set()
        for task in tasks:
            for name in task.tools_allowed:
                if name not in self._catalog:
                    missing.add(name)
        if missing:
            available = ", ".join(self.tool_names) or "(none)"
            unknown = ", ".join(sorted(missing))
            raise ValueError(
                f"Unknown tool(s) for this MCP server: {unknown}. "
                f"Available: {available}"
            )

    def definitions_for(self, allowed_names: list[str]) -> list[AnthropicToolDef]:
        tools: list[AnthropicToolDef] = []
        for name in allowed_names:
            try:
                tools.append(self._catalog[name])
            except KeyError as exc:
                raise ValueError(
                    f"Tool {name!r} is not exposed by the MCP server"
                ) from exc
        return tools

    @staticmethod
    def _to_anthropic(tool: Tool) -> AnthropicToolDef:
        schema = tool.inputSchema
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        return {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": schema,
        }
