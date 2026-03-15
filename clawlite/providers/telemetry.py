from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class _Call:
    latency_ms: float
    tokens_in: int
    tokens_out: int
    error: bool
    ts: float


@dataclass
class ProviderTelemetry:
    """Per-model in-process telemetry. Ring buffer of last ``max_calls`` calls."""

    model: str
    max_calls: int = 1000

    requests: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    errors: int = 0
    last_used_at: float = 0.0
    _calls: deque = field(default_factory=deque, repr=False)

    def __post_init__(self) -> None:
        self._calls: deque[_Call] = deque(maxlen=self.max_calls)

    def record(
        self,
        *,
        latency_ms: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error: bool = False,
    ) -> None:
        self.requests += 1
        self.tokens_in += max(0, int(tokens_in))
        self.tokens_out += max(0, int(tokens_out))
        if error:
            self.errors += 1
        self.last_used_at = time.time()
        self._calls.append(
            _Call(
                latency_ms=float(latency_ms),
                tokens_in=int(tokens_in),
                tokens_out=int(tokens_out),
                error=error,
                ts=self.last_used_at,
            )
        )

    def _latency_percentile(self, p: float) -> float:
        latencies = [c.latency_ms for c in self._calls if not c.error]
        if not latencies:
            return 0.0
        sorted_lat = sorted(latencies)
        idx = max(0, int(len(sorted_lat) * p / 100) - 1)
        return round(sorted_lat[idx], 2)

    def snapshot(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "requests": self.requests,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "errors": self.errors,
            "latency_p50_ms": self._latency_percentile(50),
            "latency_p95_ms": self._latency_percentile(95),
            "last_used_at": self.last_used_at,
        }


class TelemetryRegistry:
    """Global registry of per-model ProviderTelemetry instances."""

    def __init__(self) -> None:
        self._metrics: dict[str, ProviderTelemetry] = {}

    def get(self, model: str) -> ProviderTelemetry:
        if model not in self._metrics:
            self._metrics[model] = ProviderTelemetry(model=model)
        return self._metrics[model]

    def record(
        self,
        model: str,
        *,
        latency_ms: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error: bool = False,
    ) -> None:
        self.get(model).record(
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            error=error,
        )

    def snapshot_all(self) -> list[dict[str, Any]]:
        return [m.snapshot() for m in self._metrics.values()]


# Global singleton — imported by LiteLLMProvider and FailoverProvider
_registry = TelemetryRegistry()


def get_telemetry_registry() -> TelemetryRegistry:
    return _registry
