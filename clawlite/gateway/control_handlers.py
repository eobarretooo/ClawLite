from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

from clawlite.core.memory_monitor import MemoryMonitor
from clawlite.core.skills import skills_doctor_report, skills_managed_report, skills_sync_report, skills_validate_report


@dataclass
class GatewayControlHandlers:
    auth_guard: Any
    diagnostics_require_auth: bool
    runtime: Any
    heartbeat_enabled: bool
    memory_snapshot_create_fn: Callable[[Any, str], dict[str, Any]]
    memory_snapshot_rollback_fn: Callable[[Any, str], dict[str, Any]]
    submit_heartbeat_wake: Callable[[], Awaitable[Any]]
    submit_proactive_wake: Callable[[], Awaitable[Any]]
    self_evolution_runner_state: dict[str, Any]

    def _check_control(self, request: Request) -> None:
        self.auth_guard.check_http(
            request=request,
            scope="control",
            diagnostics_auth=self.diagnostics_require_auth,
            require_token_if_configured=True,
            allow_dashboard_session=True,
        )

    def _require_channel(self, channel_name: str) -> Any:
        channel = self.runtime.channels.get_channel(channel_name)
        if channel is None:
            raise HTTPException(status_code=404, detail=f"channel_not_available:{channel_name}")
        return channel

    def _require_channel_operator(self, channel_name: str, operator_name: str) -> Callable[..., Any]:
        channel = self._require_channel(channel_name)
        operator = getattr(channel, operator_name, None)
        if not callable(operator):
            raise HTTPException(status_code=400, detail=f"channel_operator_action_not_supported:{channel_name}")
        return operator

    async def channels_replay(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        summary = await self.runtime.channels.operator_replay_dead_letters(
            limit=max(1, min(int(payload.limit or 25), 200)),
            channel=str(payload.channel or "").strip(),
            reason=str(payload.reason or "").strip(),
            session_id=str(payload.session_id or "").strip(),
            reasons=[str(item or "").strip() for item in list(payload.reasons or []) if str(item or "").strip()],
        )
        return {"ok": True, "summary": summary}

    async def channels_recover(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        summary = await self.runtime.channels.operator_recover_channels(
            channel=str(payload.channel or "").strip(),
            force=bool(payload.force),
        )
        return {"ok": True, "summary": summary}

    async def channels_inbound_replay(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        summary = await self.runtime.channels.operator_replay_inbound(
            limit=max(1, min(int(payload.limit or 100), 500)),
            channel=str(payload.channel or "").strip(),
            session_id=str(payload.session_id or "").strip(),
            force=bool(payload.force),
        )
        return {"ok": True, "summary": summary}

    async def telegram_refresh(self, request: Request, payload: Any) -> dict[str, Any]:
        del payload
        self._check_control(request)
        operator = self._require_channel_operator("telegram", "operator_refresh_transport")
        summary = await operator()
        return {"ok": True, "summary": summary}

    async def telegram_pairing_approve(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        operator = self._require_channel_operator("telegram", "operator_approve_pairing")
        summary = await operator(str(payload.code or ""))
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def telegram_pairing_reject(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        operator = self._require_channel_operator("telegram", "operator_reject_pairing")
        summary = await operator(str(payload.code or ""))
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def telegram_pairing_revoke(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        operator = self._require_channel_operator("telegram", "operator_revoke_pairing")
        summary = await operator(str(payload.entry or ""))
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def telegram_offset_commit(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        operator = self._require_channel_operator("telegram", "operator_force_commit_offset")
        summary = await operator(int(payload.update_id or 0))
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def telegram_offset_sync(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        operator = self._require_channel_operator("telegram", "operator_sync_next_offset")
        summary = await operator(int(payload.next_offset or 0), allow_reset=bool(payload.allow_reset))
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def telegram_offset_reset(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        if not bool(payload.confirm):
            raise HTTPException(status_code=400, detail="confirmation_required")
        operator = self._require_channel_operator("telegram", "operator_sync_next_offset")
        summary = await operator(0, allow_reset=True)
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def supervisor_recover(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        if self.runtime.supervisor is None:
            raise HTTPException(status_code=404, detail="supervisor_not_available")
        summary = await self.runtime.supervisor.operator_recover_components(
            component=str(payload.component or "").strip(),
            force=bool(payload.force),
            reason=str(payload.reason or "operator_recover").strip() or "operator_recover",
        )
        return {"ok": True, "summary": summary}

    async def provider_recover(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        operator_clear = getattr(self.runtime.engine.provider, "operator_clear_suppression", None)
        if not callable(operator_clear):
            raise HTTPException(status_code=400, detail="provider_operator_action_not_supported")
        summary = operator_clear(role=str(payload.role or "").strip(), model=str(payload.model or "").strip())
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def autonomy_wake(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        normalized_kind = str(payload.kind or "proactive").strip().lower() or "proactive"
        if normalized_kind == "proactive":
            result = await self.submit_proactive_wake()
        elif normalized_kind == "heartbeat":
            result = await self.submit_heartbeat_wake()
        else:
            raise HTTPException(status_code=400, detail=f"unsupported_autonomy_wake_kind:{normalized_kind}")
        return {"ok": True, "summary": {"kind": normalized_kind, "result": result}}

    async def memory_suggest_refresh(self, request: Request, payload: Any) -> dict[str, Any]:
        del payload
        self._check_control(request)
        monitor = self.runtime.memory_monitor or MemoryMonitor(self.runtime.engine.memory)
        source = "scan"
        try:
            suggestions = await monitor.scan()
        except Exception:
            suggestions = monitor.pending()
            source = "pending_fallback"
        rows = [item.to_payload() for item in suggestions]
        rows.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))))
        summary = {
            "ok": True,
            "refresh": True,
            "source": source,
            "count": len(rows),
            "suggestions": rows,
            "pending_path": str(monitor.suggestions_path),
        }
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def skills_refresh(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        refresh = self.runtime.skills_loader.refresh(force=bool(payload.force))
        diagnostics = self.runtime.skills_loader.diagnostics_report()
        summary = {
            "ok": True,
            "refresh": refresh,
            "skills": dict(diagnostics.get("summary", {}) or {}),
            "watcher": dict(diagnostics.get("watcher", {}) or {}),
            "contract_issues": dict(diagnostics.get("contract_issues", {}) or {}),
            "missing_requirements": dict(diagnostics.get("missing_requirements", {}) or {}),
        }
        return {"ok": True, "summary": summary}

    async def skills_doctor(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        diagnostics = self.runtime.skills_loader.diagnostics_report()
        summary = skills_doctor_report(
            diagnostics,
            include_all=bool(payload.include_all),
            status=str(payload.status or ""),
            source=str(payload.source or ""),
            query=str(payload.query or ""),
        )
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def skills_validate(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        summary = skills_validate_report(
            self.runtime.skills_loader,
            force=bool(payload.force),
            include_all=bool(payload.include_all),
            status=str(payload.status or ""),
            source=str(payload.source or ""),
            query=str(payload.query or ""),
        )
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def skills_sync(self, request: Request, payload: Any) -> dict[str, Any]:
        del payload
        self._check_control(request)
        summary = await asyncio.to_thread(skills_sync_report, self.runtime.skills_loader)
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def skills_managed(self, request: Request, *, status: str = "", query: str = "") -> dict[str, Any]:
        self._check_control(request)
        summary = skills_managed_report(
            self.runtime.skills_loader,
            status=str(status or ""),
            query=str(query or ""),
        )
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def memory_snapshot_create(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        summary = self.memory_snapshot_create_fn(self.runtime.config, tag=str(payload.tag or ""))
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def memory_snapshot_rollback(self, request: Request, payload: Any) -> dict[str, Any]:
        self._check_control(request)
        if not bool(payload.confirm):
            raise HTTPException(status_code=400, detail="confirmation_required")
        summary = self.memory_snapshot_rollback_fn(self.runtime.config, version_id=str(payload.version_id or ""))
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def discord_refresh(self, request: Request, payload: Any) -> dict[str, Any]:
        del payload
        self._check_control(request)
        operator = self._require_channel_operator("discord", "operator_refresh_transport")
        summary = await operator()
        return {"ok": bool(summary.get("ok", False)), "summary": summary}

    async def heartbeat_trigger(self, request: Request) -> dict[str, Any]:
        self._check_control(request)
        if not self.heartbeat_enabled:
            raise HTTPException(status_code=409, detail="heartbeat_disabled")
        decision = await self.runtime.heartbeat.trigger_now(self.submit_heartbeat_wake)
        return {
            "ok": True,
            "decision": {
                "action": decision.action,
                "reason": decision.reason,
                "text": decision.text,
            },
        }

    async def self_evolution_status(self, request: Request) -> dict[str, Any]:
        self._check_control(request)
        evo = self.runtime.self_evolution
        if evo is None:
            return {"enabled": False, "status": {}, "runner": {}, "recent": []}
        recent = evo.log.recent(10)
        return {
            "enabled": evo.enabled,
            "status": evo.status(),
            "runner": dict(self.self_evolution_runner_state),
            "recent": recent,
        }

    async def self_evolution_trigger(self, request: Request) -> dict[str, Any]:
        self._check_control(request)
        evo = self.runtime.self_evolution
        if evo is None:
            raise HTTPException(status_code=404, detail="self_evolution_not_configured")
        payload: Any = {}
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        dry_run = bool(payload.get("dry_run", False)) if isinstance(payload, dict) else False
        status = await evo.run_once(force=True, dry_run=dry_run)
        return {"ok": True, "status": status, "runner": dict(self.self_evolution_runner_state)}
