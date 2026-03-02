from __future__ import annotations

from typing import Any

from clawlite.runtime.codex_provider import run_codex_oauth
from clawlite.providers.base import LLMProvider, LLMResult


class CodexProvider(LLMProvider):
    def __init__(self, *, model: str, access_token: str, account_id: str, timeout: float = 30.0) -> None:
        self.model = model
        self.access_token = access_token
        self.account_id = account_id
        self.timeout = timeout

    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResult:
        prompt = "\n".join(str(row.get("content", "")) for row in messages if row.get("role") != "system")
        text = run_codex_oauth(
            prompt=prompt,
            model=self.model,
            access_token=self.access_token,
            account_id=self.account_id,
            timeout=self.timeout,
        )
        return LLMResult(text=text, model=self.model, tool_calls=[], metadata={"provider": "codex"})
