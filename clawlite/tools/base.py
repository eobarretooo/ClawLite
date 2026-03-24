from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolContext:
    session_id: str
    channel: str = ""
    user_id: str = ""


@dataclass(slots=True)
class ToolHealthResult:
    ok: bool
    latency_ms: float
    detail: str


class ToolError(RuntimeError):
    """Structured error raised by ToolRegistry for all tool failures."""

    def __init__(
        self,
        tool_name: str,
        code: str,
        *,
        recoverable: bool = False,
        retry_hint: str = "",
        cause: BaseException | None = None,
    ) -> None:
        self.tool_name = str(tool_name)
        self.code = str(code)
        self.recoverable = bool(recoverable)
        self.retry_hint = str(retry_hint or "")
        super().__init__(f"tool_error:{self.tool_name}:{self.code}")
        if cause is not None:
            self.__cause__ = cause


class ToolTimeoutError(ToolError):
    def __init__(self, tool_name: str, timeout_s: float) -> None:
        self.timeout_s = float(timeout_s)
        super().__init__(
            tool_name,
            f"timeout:{timeout_s}s",
            recoverable=True,
            retry_hint="increase timeout or retry later",
        )


class Tool(ABC):
    """Tool contract with OpenAI function-calling JSON schema."""

    name: str
    description: str
    cacheable: bool = False
    default_timeout_s: float | None = None

    @abstractmethod
    def args_schema(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        raise NotImplementedError

    async def health_check(self) -> ToolHealthResult:
        return ToolHealthResult(ok=True, latency_ms=0.0, detail="no_check")

    def export_schema(self) -> dict[str, Any]:
        default_timeout_s = self.default_timeout_s
        normalized_timeout = None
        if default_timeout_s is not None:
            try:
                normalized_timeout = float(default_timeout_s)
            except (TypeError, ValueError):
                normalized_timeout = None
        return {
            "name": self.name,
            "description": self.description,
            "cacheable": bool(self.cacheable),
            "default_timeout_s": normalized_timeout,
            "parameters": self.args_schema(),
        }
