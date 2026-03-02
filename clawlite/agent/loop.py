from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class AgentRequest:
    prompt: str
    session_id: str = ""
    skill: str = ""
    workspace_path: str | None = None
    learning: bool = False


@dataclass(frozen=True)
class AgentResponse:
    text: str
    meta: dict[str, Any]


@dataclass
class AgentLoop:
    """Loop único do agente para todos os entrypoints do runtime."""

    def run_with_meta(
        self,
        *,
        prompt: str,
        skill: str = "",
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        from clawlite.core import agent as core_agent

        return core_agent._run_task_with_meta_impl(
            prompt=prompt,
            skill=skill,
            session_id=session_id,
            workspace_path=workspace_path,
        )

    async def run_with_meta_async(
        self,
        *,
        prompt: str,
        skill: str = "",
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        from clawlite.core import agent as core_agent

        return await core_agent._run_task_with_meta_async_impl(
            prompt=prompt,
            skill=skill,
            session_id=session_id,
            workspace_path=workspace_path,
        )

    def stream_with_meta(
        self,
        *,
        prompt: str,
        skill: str = "",
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> tuple[Iterator[str], dict[str, Any]]:
        from clawlite.core import agent as core_agent

        return core_agent._run_task_stream_with_meta_impl(
            prompt=prompt,
            skill=skill,
            session_id=session_id,
            workspace_path=workspace_path,
        )

    def run_with_learning(
        self,
        *,
        prompt: str,
        skill: str = "",
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> str:
        from clawlite.core import agent as core_agent

        return core_agent._run_task_with_learning_impl(
            prompt=prompt,
            skill=skill,
            session_id=session_id,
            workspace_path=workspace_path,
        )

    async def run_with_learning_async(
        self,
        *,
        prompt: str,
        skill: str = "",
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> str:
        from clawlite.core import agent as core_agent

        return await core_agent._run_task_with_learning_async_impl(
            prompt=prompt,
            skill=skill,
            session_id=session_id,
            workspace_path=workspace_path,
        )

    def stream_with_learning(
        self,
        *,
        prompt: str,
        skill: str = "",
        session_id: str = "",
        workspace_path: str | None = None,
    ) -> Iterator[str]:
        from clawlite.core import agent as core_agent

        return core_agent._run_task_stream_with_learning_impl(
            prompt=prompt,
            skill=skill,
            session_id=session_id,
            workspace_path=workspace_path,
        )

    async def process(
        self,
        *,
        prompt: str,
        session_id: str = "",
        workspace_path: str | None = None,
        learning: bool = False,
    ) -> str:
        if learning:
            return await self.run_with_learning_async(
                prompt=prompt,
                session_id=session_id,
                workspace_path=workspace_path,
            )
        output, _meta = await self.run_with_meta_async(
            prompt=prompt,
            session_id=session_id,
            workspace_path=workspace_path,
        )
        return output

    def process_request_sync(self, request: AgentRequest) -> AgentResponse:
        req = request
        if req.learning:
            text = self.run_with_learning(
                prompt=req.prompt,
                session_id=req.session_id,
                skill=req.skill,
                workspace_path=req.workspace_path,
            )
            return AgentResponse(text=text, meta={"mode": "learning", "reason": "agent-loop"})

        text, meta = self.run_with_meta(
            prompt=req.prompt,
            session_id=req.session_id,
            skill=req.skill,
            workspace_path=req.workspace_path,
        )
        return AgentResponse(text=text, meta=meta)

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        req = request
        if req.learning:
            text = await self.run_with_learning_async(
                prompt=req.prompt,
                session_id=req.session_id,
                skill=req.skill,
                workspace_path=req.workspace_path,
            )
            return AgentResponse(text=text, meta={"mode": "learning", "reason": "agent-loop"})

        text, meta = await self.run_with_meta_async(
            prompt=req.prompt,
            session_id=req.session_id,
            skill=req.skill,
            workspace_path=req.workspace_path,
        )
        return AgentResponse(text=text, meta=meta)


_LOOP: AgentLoop | None = None
_LOCK = asyncio.Lock()


async def get_agent_loop_async() -> AgentLoop:
    global _LOOP
    async with _LOCK:
        if _LOOP is None:
            _LOOP = AgentLoop()
        return _LOOP


def get_agent_loop() -> AgentLoop:
    global _LOOP
    if _LOOP is None:
        _LOOP = AgentLoop()
    return _LOOP
