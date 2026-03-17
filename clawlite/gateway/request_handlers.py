from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from loguru import logger

from clawlite.utils.logging import bind_event


@dataclass
class GatewayRequestHandlers:
    auth_guard: Any
    diagnostics_require_auth: bool
    runtime: Any
    dashboard_asset_root: str
    dashboard_bootstrap_token: str
    run_engine_with_timeout_fn: Callable[[str, str], Awaitable[Any]]
    provider_error_payload_fn: Callable[[RuntimeError], tuple[int, str]]
    finalize_bootstrap_for_user_turn_fn: Callable[[str], None]
    build_tools_catalog_payload_fn: Callable[..., dict[str, Any]]
    parse_include_schema_flag_fn: Callable[[Any], bool]
    control_plane_payload_fn: Callable[[], Any]
    dashboard_asset_text_fn: Callable[[str], str]
    render_root_dashboard_html_fn: Callable[..., str]

    def _check_control(self, request: Request) -> None:
        self.auth_guard.check_http(
            request=request,
            scope="control",
            diagnostics_auth=self.diagnostics_require_auth,
        )

    async def chat(self, req: Any, request: Request) -> Any:
        self._check_control(request)
        if not str(req.session_id or "").strip() or not str(req.text or "").strip():
            raise HTTPException(status_code=400, detail="session_id and text are required")
        logger.debug("chat request received session={} chars={}", req.session_id, len(str(req.text or "")))
        try:
            out = await self.run_engine_with_timeout_fn(str(req.session_id), str(req.text))
        except RuntimeError as exc:
            status_code, detail = self.provider_error_payload_fn(exc)
            bind_event("gateway.chat", session=str(req.session_id)).error(
                "chat request failed status={} detail={}",
                status_code,
                detail,
            )
            raise HTTPException(status_code=status_code, detail=detail) from exc
        self.finalize_bootstrap_for_user_turn_fn(str(req.session_id))
        bind_event("gateway.chat", session=str(req.session_id)).info("chat response generated model={}", out.model)
        return {"text": out.text, "model": out.model}

    async def tools_catalog(self, request: Request) -> dict[str, Any]:
        self._check_control(request)
        include_schema = self.parse_include_schema_flag_fn(request.query_params)
        return self.build_tools_catalog_payload_fn(self.runtime.engine.tools.schema(), include_schema=include_schema)

    async def cron_add(self, req: Any, request: Request) -> dict[str, Any]:
        self._check_control(request)
        job_id = await self.runtime.cron.add_job(
            session_id=req.session_id,
            expression=req.expression,
            prompt=req.prompt,
            name=req.name,
        )
        return {"ok": True, "status": "created", "id": job_id}

    async def cron_list(self, *, session_id: str, request: Request) -> dict[str, Any]:
        self._check_control(request)
        return {"jobs": self.runtime.cron.list_jobs(session_id=session_id)}

    async def cron_remove(self, *, job_id: str, request: Request) -> dict[str, Any]:
        self._check_control(request)
        removed = await asyncio.to_thread(self.runtime.cron.remove_job, job_id)
        return {"ok": removed, "status": "removed" if removed else "not_found"}

    async def dashboard_css(self) -> Response:
        return Response(
            content=self.dashboard_asset_text_fn("dashboard.css"),
            media_type="text/css",
        )

    async def dashboard_js(self) -> Response:
        return Response(
            content=self.dashboard_asset_text_fn("dashboard.js"),
            media_type="application/javascript",
        )

    async def root(self) -> HTMLResponse:
        control_plane = self.control_plane_payload_fn()
        return HTMLResponse(
            content=self.render_root_dashboard_html_fn(
                control_plane=control_plane,
                dashboard_asset_root=self.dashboard_asset_root,
                dashboard_bootstrap_token=self.dashboard_bootstrap_token,
            ),
            status_code=200,
        )


__all__ = ["GatewayRequestHandlers"]
