from __future__ import annotations

from typing import ClassVar

from llama_index.core.tools import BaseTool


class ToolRegistry:
    """
    Singleton registry for agent tools.

    Register tools at startup; the agent retrieves all at query time.
    New tools can be added without modifying agent core code.

    Usage:
        registry = ToolRegistry.get()
        registry.register(build_my_custom_tool())
        agent = build_agent(registry=registry)
    """

    _instance: ClassVar[ToolRegistry | None] = None

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    @classmethod
    def get(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear singleton — useful in tests."""
        cls._instance = None

    def register(self, tool: BaseTool) -> "ToolRegistry":
        self._tools[tool.metadata.name] = tool
        return self

    def unregister(self, name: str) -> "ToolRegistry":
        self._tools.pop(name, None)
        return self

    def all_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={list(self._tools.keys())})"
