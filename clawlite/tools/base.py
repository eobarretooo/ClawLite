from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolContext:
    session_id: str
    channel: str = ""
    user_id: str = ""


class Tool(ABC):
    """Tool contract with OpenAI function-calling JSON schema."""

    name: str
    description: str

    @abstractmethod
    def args_schema(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        raise NotImplementedError

    def export_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_schema(),
        }
