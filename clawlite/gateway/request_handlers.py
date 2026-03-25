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
    run_engine_with_timeout_fn: Callable[..., Awaitable[Any]]
    provider_error_payload_fn: Callable[[RuntimeError], tuple[int, str]]
    finalize_bootstrap_for_user_turn_fn: Callable[[str], None]
    build_tools_catalog_payload_fn: Callable[..., dict[str, Any]]
    parse_include_schema_flag_fn: Callable[[Any], bool]
    control_plane_payload_fn: Callable[[], Any]
    dashboard_asset_text_fn: Callable[[str], str]
    render_root_dashboard_html_fn: Callable[..., str]

    def _check_control(self, request: Request, *, allow_dashboard_session: bool = False) -> None:
        self.auth_guard.check_http(
            request=request,
            scope="control",
            diagnostics_auth=self.diagnostics_require_auth,
            allow_dashboard_session=allow_dashboard_session,
        )

    def _check_sensitive_control(self, request: Request, *, allow_dashboard_session: bool = False) -> None:
        self.auth_guard.check_http(
            request=request,
            scope="control",
            diagnostics_auth=self.diagnostics_require_auth,
            require_token_if_configured=True,
            allow_dashboard_session=allow_dashboard_session,
        )

    @staticmethod
    def _cron_counts(jobs: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in jobs:
            status = str(row.get("last_status", "") or "idle").strip() or "idle"
            counts[status] = counts.get(status, 0) + 1
        return dict(sorted(counts.items()))

    def _cron_list_payload(self, *, session_id: str = "") -> dict[str, Any]:
        scoped_session = str(session_id or "").strip()
        jobs = self.runtime.cron.list_jobs(session_id=scoped_session or None)
        enabled_count = sum(1 for row in jobs if bool(row.get("enabled", False)))
        return {
            "status": self.runtime.cron.status(),
            "session_id": scoped_session,
            "count": len(jobs),
            "enabled_count": enabled_count,
            "disabled_count": max(0, len(jobs) - enabled_count),
            "status_counts": self._cron_counts(jobs),
            "jobs": jobs,
        }

    async def chat(self, req: Any, request: Request, *, allow_dashboard_session: bool = False) -> Any:
        self._check_sensitive_control(request, allow_dashboard_session=allow_dashboard_session)
        if not str(req.session_id or "").strip() or not str(req.text or "").strip():
            raise HTTPException(status_code=400, detail="session_id and text are required")
        request_state = getattr(request, "state", None)
        request_id = str(getattr(request_state, "request_id", "") or "").strip() or "-"
        logger.debug(
            "chat request received session={} request_id={} chars={}",
            req.session_id,
            request_id,
            len(str(req.text or "")),
        )
        channel = str(getattr(req, "channel", "") or "").strip() or None
        raw_chat_id = getattr(req, "chat_id", None)
        chat_id = None if raw_chat_id is None else str(raw_chat_id).strip() or None
        raw_runtime_metadata = getattr(req, "runtime_metadata", None)
        runtime_metadata = dict(raw_runtime_metadata) if isinstance(raw_runtime_metadata, dict) and raw_runtime_metadata else None
        try:
            out = await self.run_engine_with_timeout_fn(
                str(req.session_id),
                str(req.text),
                channel=channel,
                chat_id=chat_id,
                runtime_metadata=runtime_metadata,
            )
        except RuntimeError as exc:
            status_code, detail = self.provider_error_payload_fn(exc)
            bind_event("gateway.chat", session=str(req.session_id)).error(
                "chat request failed request_id={} status={} detail={}",
                request_id,
                status_code,
                detail,
            )
            raise HTTPException(status_code=status_code, detail=detail) from exc
        self.finalize_bootstrap_for_user_turn_fn(str(req.session_id))
        bind_event("gateway.chat", session=str(req.session_id)).info(
            "chat response generated request_id={} model={}",
            request_id,
            out.model,
        )
        return {"text": out.text, "model": out.model}

    async def tools_catalog(self, request: Request, *, allow_dashboard_session: bool = False) -> dict[str, Any]:
        self._check_sensitive_control(request, allow_dashboard_session=allow_dashboard_session)
        include_schema = self.parse_include_schema_flag_fn(request.query_params)
        return self.build_tools_catalog_payload_fn(self.runtime.engine.tools.schema(), include_schema=include_schema)

    async def tools_approvals(
        self,
        request: Request,
        *,
        allow_dashboard_session: bool = False,
        status: str = "pending",
        session_id: str = "",
        channel: str = "",
        tool: str = "",
        rule: str = "",
        include_grants: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        self._check_sensitive_control(request, allow_dashboard_session=allow_dashboard_session)
        tools = getattr(self.runtime.engine, "tools", None)
        normalized_status = str(status or "pending").strip().lower() or "pending"
        normalized_session = str(session_id or "").strip()
        normalized_channel = str(channel or "").strip().lower()
        normalized_tool = str(tool or "").strip().lower()
        normalized_rule = str(rule or "").strip().lower()
        max_rows = max(1, int(limit or 1))
        list_requests = getattr(tools, "approval_requests_snapshot", None)
        if not callable(list_requests):
            return {
                "ok": True,
                "status": normalized_status,
                "session_id": normalized_session,
                "channel": normalized_channel,
                "tool": normalized_tool,
                "rule": normalized_rule,
                "include_grants": bool(include_grants),
                "count": 0,
                "requests": [],
                "grant_count": 0,
                "grants": [],
            }
        requests = list_requests(
            status=normalized_status,
            session_id=normalized_session,
            channel=normalized_channel,
            tool=normalized_tool,
            rule=normalized_rule,
            limit=max_rows,
        )
        grants: list[dict[str, Any]] = []
        if include_grants:
            list_grants = getattr(tools, "approval_grants_snapshot", None)
            if callable(list_grants):
                grants = list_grants(
                    session_id=normalized_session,
                    channel=normalized_channel,
                    limit=max_rows,
                )
                if normalized_rule:
                    grants = [row for row in grants if str((row or {}).get("rule", "") or "").strip().lower() == normalized_rule]
                elif normalized_tool:
                    grants = [
                        row
                        for row in grants
                        if str((row or {}).get("rule", "") or "").strip().lower().split(":", 1)[0] == normalized_tool
                    ]
        return {
            "ok": True,
            "status": normalized_status,
            "session_id": normalized_session,
            "channel": normalized_channel,
            "tool": normalized_tool,
            "rule": normalized_rule,
            "include_grants": bool(include_grants),
            "count": len(requests),
            "requests": requests,
            "grant_count": len(grants),
            "grants": grants,
        }

    async def tools_approval_review(
        self,
        request: Request,
        *,
        allow_dashboard_session: bool = False,
        request_id: str,
        decision: str,
        actor: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        self._check_sensitive_control(request, allow_dashboard_session=allow_dashboard_session)
        tools = getattr(self.runtime.engine, "tools", None)
        review_fn = getattr(tools, "review_approval_request", None)
        if not callable(review_fn):
            raise HTTPException(status_code=501, detail="tool_approval_flow_not_enabled")

        summary = await asyncio.to_thread(
            review_fn,
            str(request_id or "").strip(),
            decision=str(decision or "").strip().lower(),
            actor="control-plane",
            note=str(note or "").strip(),
        )
        if not isinstance(summary, dict):
            raise HTTPException(status_code=500, detail="tool_approval_review_failed")
        if not bool(summary.get("ok", False)):
            error = str(summary.get("error", "tool_approval_review_failed") or "tool_approval_review_failed")
            expected_actor = str(summary.get("expected_actor", "") or "").strip()
            if error == "approval_request_not_found":
                raise HTTPException(status_code=404, detail=error)
            if error == "invalid_review_decision":
                raise HTTPException(status_code=400, detail=error)
            if error in {"approval_actor_required", "approval_actor_mismatch", "approval_channel_bound"} and expected_actor:
                raise HTTPException(status_code=400, detail=f"{error}:{expected_actor}")
            raise HTTPException(status_code=400, detail=error)
        return {"ok": True, "summary": summary}

    async def tools_grants_revoke(
        self,
        request: Request,
        *,
        allow_dashboard_session: bool = False,
        session_id: str = "",
        channel: str = "",
        rule: str = "",
    ) -> dict[str, Any]:
        self._check_sensitive_control(request, allow_dashboard_session=allow_dashboard_session)
        tools = getattr(self.runtime.engine, "tools", None)
        revoke_fn = getattr(tools, "revoke_approval_grants", None)
        if not callable(revoke_fn):
            raise HTTPException(status_code=501, detail="tool_approval_flow_not_enabled")

        summary = await asyncio.to_thread(
            revoke_fn,
            session_id=str(session_id or "").strip(),
            channel=str(channel or "").strip().lower(),
            rule=str(rule or "").strip().lower(),
        )
        if not isinstance(summary, dict) or not bool(summary.get("ok", False)):
            error = "tool_grant_revoke_failed"
            if isinstance(summary, dict):
                error = str(summary.get("error", error) or error)
            raise HTTPException(status_code=400, detail=error)
        return {"ok": True, "summary": summary}

    async def cron_add(self, req: Any, request: Request) -> dict[str, Any]:
        self._check_sensitive_control(request)
        job_id = await self.runtime.cron.add_job(
            session_id=req.session_id,
            expression=req.expression,
            prompt=req.prompt,
            name=req.name,
        )
        return {"ok": True, "status": "created", "id": job_id}

    async def cron_status(self, *, request: Request) -> dict[str, Any]:
        self._check_sensitive_control(request)
        return self._cron_list_payload()

    async def cron_list(self, *, session_id: str = "", request: Request) -> dict[str, Any]:
        self._check_sensitive_control(request)
        return self._cron_list_payload(session_id=session_id)

    async def cron_get(self, *, job_id: str, session_id: str = "", request: Request) -> dict[str, Any]:
        self._check_sensitive_control(request)
        scoped_session = str(session_id or "").strip()
        jobs = self.runtime.cron.list_jobs(session_id=scoped_session or None)
        job = next((row for row in jobs if str(row.get("id", "") or "").strip() == str(job_id or "").strip()), None)
        if job is None:
            raise HTTPException(status_code=404, detail="cron_job_not_found")
        return {"status": self.runtime.cron.status(), "job": job}

    async def cron_toggle(
        self,
        *,
        job_id: str,
        enabled: bool,
        session_id: str = "",
        request: Request,
    ) -> dict[str, Any]:
        self._check_sensitive_control(request)
        scoped_session = str(session_id or "").strip() or None
        changed = self.runtime.cron.enable_job(
            job_id,
            enabled=bool(enabled),
            session_id=scoped_session,
        )
        if not changed:
            return {"ok": False, "status": "not_found"}
        payload = await self.cron_get(job_id=job_id, session_id=str(session_id or ""), request=request)
        return {
            "ok": True,
            "status": "enabled" if enabled else "disabled",
            "cron_status": payload.get("status", {}),
            "job": payload.get("job", {}),
        }

    async def cron_remove(self, *, job_id: str, request: Request) -> dict[str, Any]:
        self._check_sensitive_control(request)
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
