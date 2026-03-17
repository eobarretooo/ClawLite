from __future__ import annotations

import importlib
import json
from collections import defaultdict
from dataclasses import asdict
from typing import Any

from clawlite.bus.events import InboundEvent, OutboundEvent
from clawlite.bus.queue import MessageQueue


class RedisMessageQueue(MessageQueue):
    """Redis-backed queue for inbound/outbound events with local fallbacks for auxiliary state."""

    def __init__(
        self,
        *,
        redis_url: str,
        prefix: str = "clawlite:bus",
        client_factory: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._redis_url = str(redis_url or "").strip() or "redis://127.0.0.1:6379/0"
        self._prefix = str(prefix or "").strip() or "clawlite:bus"
        self._client_factory = client_factory
        self._client: Any | None = None
        self._connected = False
        self._last_error = ""
        self._inbound_size_estimate = 0
        self._outbound_size_estimate = 0

    @property
    def inbound_key(self) -> str:
        return f"{self._prefix}:inbound"

    @property
    def outbound_key(self) -> str:
        return f"{self._prefix}:outbound"

    def _build_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory(self._redis_url)
        try:
            redis_asyncio = importlib.import_module("redis.asyncio")
        except Exception as exc:
            raise RuntimeError("redis_backend_requires_dependency:redis") from exc
        return redis_asyncio.from_url(self._redis_url, decode_responses=True)

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    @staticmethod
    def _coerce_blpop_payload(value: Any) -> str:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            candidate = value[1]
        else:
            candidate = value
        if isinstance(candidate, bytes):
            return candidate.decode("utf-8", errors="replace")
        return str(candidate or "")

    async def connect(self) -> None:
        client = self._ensure_client()
        try:
            ping = getattr(client, "ping", None)
            if callable(ping):
                await ping()
            self._connected = True
            self._last_error = ""
        except Exception as exc:
            self._connected = False
            self._last_error = str(exc)
            raise RuntimeError(f"redis_bus_connect_failed:{exc}") from exc

    async def close(self) -> None:
        client = self._client
        self._connected = False
        if client is not None:
            close_fn = getattr(client, "aclose", None)
            if callable(close_fn):
                await close_fn()
            else:
                close_fn = getattr(client, "close", None)
                if callable(close_fn):
                    result = close_fn()
                    if hasattr(result, "__await__"):
                        await result
        await super().close()

    async def publish_inbound(self, event: InboundEvent, *, nowait: bool = False) -> None:
        del nowait
        client = self._ensure_client()
        payload = json.dumps(asdict(event), ensure_ascii=False)
        await client.rpush(self.inbound_key, payload)
        self._inbound_size_estimate += 1
        self._inbound_published += 1

        if self._journal is not None:
            row_id = self._journal.append_inbound(event)
            if row_id is not None:
                self._inbound_journal_ids[event.correlation_id] = row_id

        for queue in tuple(self._topics.get(event.channel, ())):
            await queue.put(event)
        for queue in tuple(self._topics.get("*", ())):
            await queue.put(event)

    async def next_inbound(self) -> InboundEvent:
        client = self._ensure_client()
        raw = await client.blpop(self.inbound_key, timeout=0)
        payload = json.loads(self._coerce_blpop_payload(raw))
        event = InboundEvent(**payload)
        if self._inbound_size_estimate > 0:
            self._inbound_size_estimate -= 1
        if self._journal is not None:
            row_id = self._inbound_journal_ids.pop(event.correlation_id, None)
            if row_id is not None:
                self._journal.ack_inbound(row_id)
        return event

    async def publish_outbound(self, event: OutboundEvent) -> None:
        client = self._ensure_client()
        payload = json.dumps(asdict(event), ensure_ascii=False)
        await client.rpush(self.outbound_key, payload)
        self._outbound_size_estimate += 1
        self._outbound_created_at.append(str(event.created_at))
        self._outbound_enqueued += 1
        if self._journal is not None:
            row_id = self._journal.append_outbound(event)
            if row_id is not None:
                self._outbound_journal_ids[event.correlation_id] = row_id

    async def next_outbound(self) -> OutboundEvent:
        client = self._ensure_client()
        raw = await client.blpop(self.outbound_key, timeout=0)
        payload = json.loads(self._coerce_blpop_payload(raw))
        event = OutboundEvent(**payload)
        if self._outbound_size_estimate > 0:
            self._outbound_size_estimate -= 1
        if self._outbound_created_at:
            self._outbound_created_at.popleft()
        if self._journal is not None:
            row_id = self._outbound_journal_ids.pop(event.correlation_id, None)
            if row_id is not None:
                self._journal.ack_outbound(row_id)
        return event

    def stats(self) -> dict[str, Any]:
        payload = super().stats()
        payload["backend"] = "redis"
        payload["redis_url"] = self._redis_url
        payload["redis_prefix"] = self._prefix
        payload["redis_connected"] = self._connected
        payload["redis_last_error"] = self._last_error
        payload["inbound_size"] = max(0, int(self._inbound_size_estimate))
        payload["outbound_size"] = max(0, int(self._outbound_size_estimate))
        return payload


__all__ = ["RedisMessageQueue"]
