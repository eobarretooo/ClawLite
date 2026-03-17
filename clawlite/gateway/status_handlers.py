from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request


@dataclass
class GatewayStatusHandlers:
    auth_guard: Any
    diagnostics_require_auth: bool
    cfg: Any
    runtime: Any
    lifecycle: Any
    status_payload_fn: Callable[[], Any]
    dashboard_state_payload_fn: Callable[[], dict[str, Any]]
    diagnostics_payload_fn: Callable[[], Awaitable[Any]]
    token_payload_fn: Callable[[], dict[str, Any]]

    def _check(self, request: Request, *, scope: str) -> None:
        self.auth_guard.check_http(
            request=request,
            scope=scope,
            diagnostics_auth=self.diagnostics_require_auth,
        )

    async def health(self, request: Request) -> dict[str, Any]:
        self._check(request, scope="health")
        return {
            "ok": True,
            "ready": self.lifecycle.ready,
            "phase": self.lifecycle.phase,
            "channels": self.runtime.channels.status(),
            "queue": self.runtime.bus.stats(),
        }

    async def health_config(self, request: Request) -> dict[str, Any]:
        self._check(request, scope="health")
        from clawlite.config.health import config_health

        return config_health(self.cfg)

    async def health_tools(self, request: Request) -> dict[str, Any]:
        self._check(request, scope="health")
        results: list[dict[str, Any]] = []
        for name in sorted(self.runtime.tools._tools.keys()):
            tool = self.runtime.tools._tools[name]
            try:
                hr = await tool.health_check()
                results.append({"tool": name, "ok": hr.ok, "latency_ms": hr.latency_ms, "detail": hr.detail})
            except Exception as exc:
                results.append({"tool": name, "ok": False, "latency_ms": 0.0, "detail": str(exc)})
        return {"ok": all(r["ok"] for r in results), "tools": results}

    async def health_providers(self, request: Request) -> dict[str, Any]:
        self._check(request, scope="health")
        provider = self.runtime.engine.provider
        warmup_fn = getattr(provider, "warmup", None)
        if callable(warmup_fn):
            result = await warmup_fn()
        else:
            result = {"ok": True, "detail": "warmup_not_supported"}
        return {"ok": result.get("ok", False), "provider": result}

    async def metrics_providers(self, request: Request) -> dict[str, Any]:
        self._check(request, scope="health")
        from clawlite.providers.telemetry import get_telemetry_registry

        return {"metrics": get_telemetry_registry().snapshot_all()}

    async def status(self, request: Request) -> Any:
        self._check(request, scope="control")
        return self.status_payload_fn()

    async def dashboard_state(self, request: Request) -> dict[str, Any]:
        self._check(request, scope="control")
        return self.dashboard_state_payload_fn()

    async def diagnostics(self, request: Request) -> Any:
        if not self.cfg.gateway.diagnostics.enabled:
            raise HTTPException(status_code=404, detail="diagnostics_disabled")
        self._check(request, scope="diagnostics")
        return await self.diagnostics_payload_fn()

    async def api_token(self, request: Request) -> dict[str, Any]:
        self._check(request, scope="control")
        return self.token_payload_fn()


__all__ = ["GatewayStatusHandlers"]
