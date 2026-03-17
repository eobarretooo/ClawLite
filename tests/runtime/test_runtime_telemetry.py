from __future__ import annotations

from clawlite.runtime.telemetry import configure_observability, telemetry_status


def test_configure_observability_disabled_keeps_noop_status() -> None:
    payload = configure_observability(enabled=False)
    assert payload["enabled"] is False
    assert payload["configured"] is False
    assert payload["last_error"] == ""
    assert telemetry_status()["enabled"] is False


def test_configure_observability_handles_missing_dependency(monkeypatch) -> None:
    def _boom(name: str):
        raise ImportError(f"missing:{name}")

    monkeypatch.setattr("clawlite.runtime.telemetry.importlib.import_module", _boom)

    payload = configure_observability(enabled=True, endpoint="http://otel:4317")
    assert payload["enabled"] is True
    assert payload["configured"] is False
    assert "missing:opentelemetry.trace" in payload["last_error"]
