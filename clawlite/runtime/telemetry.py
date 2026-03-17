from __future__ import annotations

import importlib
from typing import Any, Callable


class _NoopSpan:
    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def set_attribute(self, name: str, value: Any) -> None:
        del name, value

    def record_exception(self, exc: Exception) -> None:
        del exc


class _NoopTracer:
    def start_as_current_span(self, name: str) -> _NoopSpan:
        del name
        return _NoopSpan()


_NOOP_TRACER = _NoopTracer()
_TRACER_FACTORY: Callable[[str], Any] | None = None
_TELEMETRY_STATUS: dict[str, Any] = {
    "enabled": False,
    "configured": False,
    "exporter": "",
    "endpoint": "",
    "service_name": "clawlite",
    "service_namespace": "",
    "last_error": "",
}


def set_test_tracer_factory(factory: Callable[[str], Any] | None) -> None:
    global _TRACER_FACTORY
    _TRACER_FACTORY = factory


def get_tracer(name: str) -> Any:
    if _TRACER_FACTORY is not None:
        return _TRACER_FACTORY(str(name or "clawlite"))
    try:
        trace = importlib.import_module("opentelemetry.trace")
        return trace.get_tracer(str(name or "clawlite"))
    except Exception:
        return _NOOP_TRACER


def set_span_attributes(span: Any, attributes: dict[str, Any]) -> None:
    for key, value in dict(attributes or {}).items():
        if value is None:
            continue
        try:
            if isinstance(value, (str, bool, int, float)):
                span.set_attribute(str(key), value)
            else:
                span.set_attribute(str(key), str(value))
        except Exception:
            continue


def configure_observability(
    *,
    enabled: bool,
    endpoint: str = "",
    service_name: str = "clawlite",
    service_namespace: str = "",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    global _TELEMETRY_STATUS

    status = {
        "enabled": bool(enabled),
        "configured": False,
        "exporter": "",
        "endpoint": str(endpoint or "").strip(),
        "service_name": str(service_name or "clawlite").strip() or "clawlite",
        "service_namespace": str(service_namespace or "").strip(),
        "last_error": "",
    }
    if not enabled:
        _TELEMETRY_STATUS = status
        return dict(_TELEMETRY_STATUS)

    try:
        trace = importlib.import_module("opentelemetry.trace")
        sdk_trace = importlib.import_module("opentelemetry.sdk.trace")
        resources = importlib.import_module("opentelemetry.sdk.resources")
        resource_attrs = {"service.name": status["service_name"]}
        if status["service_namespace"]:
            resource_attrs["service.namespace"] = status["service_namespace"]
        resource = resources.Resource.create(resource_attrs)
        provider = sdk_trace.TracerProvider(resource=resource)
        endpoint_value = status["endpoint"]
        if endpoint_value:
            exporter_mod = importlib.import_module("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
            export_mod = importlib.import_module("opentelemetry.sdk.trace.export")
            exporter = exporter_mod.OTLPSpanExporter(
                endpoint=endpoint_value,
                headers=dict(headers or {}),
            )
            provider.add_span_processor(export_mod.BatchSpanProcessor(exporter))
            status["exporter"] = "otlp"
        else:
            status["exporter"] = "sdk"
        trace.set_tracer_provider(provider)
        status["configured"] = True
    except Exception as exc:
        status["last_error"] = str(exc)
    _TELEMETRY_STATUS = status
    return dict(_TELEMETRY_STATUS)


def telemetry_status() -> dict[str, Any]:
    return dict(_TELEMETRY_STATUS)


__all__ = [
    "configure_observability",
    "get_tracer",
    "set_span_attributes",
    "set_test_tracer_factory",
    "telemetry_status",
]
