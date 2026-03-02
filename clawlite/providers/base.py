from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class LLMResult:
    text: str
    model: str
    tool_calls: list[ToolCall]
    metadata: dict[str, Any]


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResult:
        raise NotImplementedError
