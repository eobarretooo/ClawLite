from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class InboundEnvelope:
    channel: str
    session_id: str
    text: str
    reply_future: asyncio.Future[str] | None = None


@dataclass
class OutboundEnvelope:
    channel: str
    session_id: str
    text: str
    instance_key: str = ""


class MessageBus:
    """Barramento assíncrono para desacoplar canais do core."""

    def __init__(
        self,
        *,
        inbound_handler: Callable[[InboundEnvelope], Awaitable[str]],
        outbound_handler: Callable[[OutboundEnvelope], Awaitable[None]],
    ) -> None:
        self._inbound_handler = inbound_handler
        self._outbound_handler = outbound_handler
        self._inbound_q: asyncio.Queue[InboundEnvelope] = asyncio.Queue()
        self._outbound_q: asyncio.Queue[OutboundEnvelope] = asyncio.Queue()
        self._inbound_worker: asyncio.Task[None] | None = None
        self._outbound_worker: asyncio.Task[None] | None = None
        self._start_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._start_lock:
            if self._inbound_worker and not self._inbound_worker.done():
                return
            self._inbound_worker = asyncio.create_task(self._run_inbound_worker())
            self._outbound_worker = asyncio.create_task(self._run_outbound_worker())

    async def stop(self) -> None:
        workers = [self._inbound_worker, self._outbound_worker]
        self._inbound_worker = None
        self._outbound_worker = None
        for task in workers:
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def request_reply(self, *, channel: str, session_id: str, text: str, timeout_s: float = 120.0) -> str:
        await self.start()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        await self._inbound_q.put(
            InboundEnvelope(
                channel=str(channel or "").strip().lower(),
                session_id=str(session_id or "").strip(),
                text=str(text or ""),
                reply_future=fut,
            )
        )
        return await asyncio.wait_for(fut, timeout=timeout_s)

    async def publish_outbound(
        self,
        *,
        channel: str,
        session_id: str,
        text: str,
        instance_key: str = "",
    ) -> None:
        await self.start()
        await self._outbound_q.put(
            OutboundEnvelope(
                channel=str(channel or "").strip().lower(),
                session_id=str(session_id or "").strip(),
                text=str(text or ""),
                instance_key=str(instance_key or "").strip(),
            )
        )

    async def _run_inbound_worker(self) -> None:
        while True:
            env = await self._inbound_q.get()
            if env.reply_future is not None and env.reply_future.done():
                continue
            try:
                out = await self._inbound_handler(env)
                if env.reply_future is not None and not env.reply_future.done():
                    env.reply_future.set_result(str(out or ""))
            except Exception as exc:
                if env.reply_future is not None and not env.reply_future.done():
                    env.reply_future.set_exception(exc)

    async def _run_outbound_worker(self) -> None:
        while True:
            env = await self._outbound_q.get()
            await self._outbound_handler(env)
