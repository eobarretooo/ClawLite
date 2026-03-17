from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from clawlite.gateway.status_handlers import GatewayStatusHandlers


def _build_handlers(*, diagnostics_enabled: bool = True) -> GatewayStatusHandlers:
    auth_guard = SimpleNamespace(check_http=lambda **kwargs: None, token="secret", mode="required", header_name="Authorization", query_param="token")
    runtime = SimpleNamespace(
        channels=SimpleNamespace(status=lambda: {"ok": True}),
        bus=SimpleNamespace(stats=lambda: {"queued": 0}),
        tools=SimpleNamespace(
            _tools={
                "ok": SimpleNamespace(health_check=AsyncMock(return_value=SimpleNamespace(ok=True, latency_ms=1.5, detail="ready"))),
                "bad": SimpleNamespace(health_check=AsyncMock(side_effect=RuntimeError("boom"))),
            }
        ),
        engine=SimpleNamespace(provider=SimpleNamespace()),
    )
    lifecycle = SimpleNamespace(ready=True, phase="running")
    cfg = SimpleNamespace(gateway=SimpleNamespace(diagnostics=SimpleNamespace(enabled=diagnostics_enabled)))
    return GatewayStatusHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=False,
        cfg=cfg,
        runtime=runtime,
        lifecycle=lifecycle,
        status_payload_fn=lambda: {"ok": True},
        dashboard_state_payload_fn=lambda: {"dashboard": True},
        diagnostics_payload_fn=AsyncMock(return_value={"diagnostics": True}),
        token_payload_fn=lambda: {"token_configured": True},
    )


def test_status_handlers_health_tools_aggregates_success_and_failure() -> None:
    async def _scenario() -> None:
        handlers = _build_handlers()
        payload = await handlers.health_tools(SimpleNamespace())
        assert payload["ok"] is False
        assert payload["tools"][0]["tool"] == "bad"
        assert payload["tools"][1]["tool"] == "ok"

    asyncio.run(_scenario())


def test_status_handlers_diagnostics_respects_toggle() -> None:
    async def _scenario() -> None:
        handlers = _build_handlers(diagnostics_enabled=False)
        try:
            await handlers.diagnostics(SimpleNamespace())
        except HTTPException as exc:
            assert exc.status_code == 404
            assert exc.detail == "diagnostics_disabled"
        else:
            raise AssertionError("expected diagnostics_disabled")

    asyncio.run(_scenario())
