"""Tests for ProviderTelemetry and TelemetryRegistry."""
from __future__ import annotations

import time

import pytest

from clawlite.providers.telemetry import ProviderTelemetry, TelemetryRegistry


def test_record_increments_counters():
    t = ProviderTelemetry(model="gpt-4")
    t.record(latency_ms=100.0, tokens_in=10, tokens_out=5)
    t.record(latency_ms=200.0, tokens_in=20, tokens_out=15)
    assert t.requests == 2
    assert t.tokens_in == 30
    assert t.tokens_out == 20
    assert t.errors == 0


def test_record_error_increments_errors():
    t = ProviderTelemetry(model="gpt-4")
    t.record(latency_ms=50.0, error=True)
    assert t.errors == 1
    assert t.requests == 1


def test_latency_p50_p95():
    t = ProviderTelemetry(model="gpt-4")
    # 10 calls with known latencies
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    for lat in latencies:
        t.record(latency_ms=lat)
    snap = t.snapshot()
    # p50 should be in the lower half, p95 near the top
    assert snap["latency_p50_ms"] <= 60.0
    assert snap["latency_p95_ms"] >= 80.0


def test_latency_excludes_errors():
    t = ProviderTelemetry(model="gpt-4")
    t.record(latency_ms=1000.0, error=True)
    t.record(latency_ms=10.0)
    snap = t.snapshot()
    # Error latencies excluded from percentile calculation
    assert snap["latency_p50_ms"] == pytest.approx(10.0, abs=1.0)


def test_ring_buffer_max_calls():
    t = ProviderTelemetry(model="gpt-4", max_calls=5)
    for i in range(10):
        t.record(latency_ms=float(i))
    # Ring buffer capped at 5
    assert len(t._calls) == 5
    # requests counter still tracks all 10
    assert t.requests == 10


def test_snapshot_structure():
    t = ProviderTelemetry(model="my-model")
    t.record(latency_ms=42.0, tokens_in=5, tokens_out=3)
    snap = t.snapshot()
    assert snap["model"] == "my-model"
    assert "requests" in snap
    assert "tokens_in" in snap
    assert "tokens_out" in snap
    assert "errors" in snap
    assert "latency_p50_ms" in snap
    assert "latency_p95_ms" in snap
    assert "last_used_at" in snap
    assert snap["last_used_at"] > 0


def test_registry_creates_models():
    reg = TelemetryRegistry()
    reg.record("model-a", latency_ms=10.0, tokens_in=1, tokens_out=1)
    reg.record("model-a", latency_ms=20.0)
    reg.record("model-b", latency_ms=5.0)
    all_snaps = reg.snapshot_all()
    assert len(all_snaps) == 2
    models = {s["model"] for s in all_snaps}
    assert models == {"model-a", "model-b"}
    a = next(s for s in all_snaps if s["model"] == "model-a")
    assert a["requests"] == 2


def test_registry_get_returns_same_instance():
    reg = TelemetryRegistry()
    t1 = reg.get("x")
    t2 = reg.get("x")
    assert t1 is t2


def test_snapshot_empty():
    t = ProviderTelemetry(model="empty")
    snap = t.snapshot()
    assert snap["latency_p50_ms"] == 0.0
    assert snap["latency_p95_ms"] == 0.0
