from __future__ import annotations

"""Tool bridge for executable SKILL.md entries.

`SkillTool` makes discovered skills runnable at runtime without changing
`registry.py` for each new skill:
- `command:` runs shell commands from SKILL metadata
- `script:` dispatches to built-in tool wrappers or external executables
"""

import asyncio
import importlib.util
import inspect
import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from clawlite.core.skills import SkillsLoader
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry
from clawlite.utils.logging import bind_event


class SkillTool(Tool):
    """Execute skills discovered by `SkillsLoader`.

    This tool is required to turn SKILL.md discovery into actual execution.
    Without it, skills would appear in prompt context but would not be callable.
    """

    name = "run_skill"
    description = "Execute a discovered SKILL.md binding with deterministic contracts."

    MAX_TIMEOUT_SECONDS = 120.0
    MAX_SKILL_ARGS = 32
    MAX_ARG_CHARS = 4000
    SUMMARY_MAX_SOURCE_CHARS = 12000

    def __init__(
        self,
        *,
        loader: SkillsLoader,
        registry: ToolRegistry,
        memory: Any | None = None,
        provider: Any | None = None,
    ) -> None:
        self.loader = loader
        self.registry = registry
        self.memory = memory
        self.provider = provider

    @staticmethod
    def _policy_reason(raw: Any) -> str:
        text = str(raw or "").strip()
        if not text:
            return "unspecified"
        return text.replace("\n", " ").replace("\r", " ")

    async def _memory_policy_allows(self, *, session_id: str) -> tuple[bool, str]:
        memory = self.memory
        if memory is None:
            return True, ""

        policy_fn = getattr(memory, "integration_policy", None)
        if not callable(policy_fn):
            return True, ""

        try:
            verdict = policy_fn("skill", session_id=session_id)
            if inspect.isawaitable(verdict):
                verdict = await verdict
        except Exception as exc:
            return False, f"policy_exception:{exc.__class__.__name__.lower()}"

        if isinstance(verdict, bool):
            return verdict, "" if verdict else "blocked"

        if isinstance(verdict, dict):
            allowed_raw = verdict.get("allowed", verdict.get("allow", verdict.get("ok", True)))
            allowed = bool(allowed_raw)
            reason = self._policy_reason(verdict.get("reason", verdict.get("message", verdict.get("detail", ""))))
            return allowed, reason if not allowed else ""

        allowed_attr = getattr(verdict, "allowed", None)
        if allowed_attr is not None:
            allowed = bool(allowed_attr)
            reason = self._policy_reason(getattr(verdict, "reason", ""))
            return allowed, reason if not allowed else ""

        return True, ""

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "input": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "timeout": {"type": "number", "default": 30},
                "query": {"type": "string"},
                "location": {"type": "string"},
                "tool_arguments": {"type": "object"},
            },
            "required": ["name"],
        }

    @staticmethod
    def _extra_args(arguments: dict[str, Any]) -> list[str]:
        values = arguments.get("args")
        if isinstance(values, list):
            return [str(item) for item in values if str(item).strip()]
        raw = str(arguments.get("input", "")).strip()
        return shlex.split(raw) if raw else []

    @classmethod
    def _guard_extra_args(cls, values: list[str]) -> str | None:
        if len(values) > cls.MAX_SKILL_ARGS:
            return f"skill_args_exceeded:max={cls.MAX_SKILL_ARGS}"
        for value in values:
            if len(value) > cls.MAX_ARG_CHARS:
                return f"skill_arg_too_large:max_chars={cls.MAX_ARG_CHARS}"
            if "\x00" in value or "\n" in value or "\r" in value:
                return "skill_arg_invalid_character"
        return None

    @classmethod
    def _timeout_value(cls, arguments: dict[str, Any]) -> float:
        raw = float(arguments.get("timeout", 30) or 30)
        if raw < 1:
            return 1.0
        if raw > cls.MAX_TIMEOUT_SECONDS:
            return cls.MAX_TIMEOUT_SECONDS
        return raw

    @staticmethod
    def _join_command(argv: list[str]) -> str:
        if not argv:
            return ""
        return shlex.join(argv)

    async def _run_command_via_exec_tool(self, *, spec_name: str, argv: list[str], timeout: float, ctx: ToolContext) -> str:
        command = self._join_command(argv)
        if not command:
            raise ValueError("empty command")
        try:
            return await self.registry.execute(
                "exec",
                {"command": command, "timeout": timeout},
                session_id=ctx.session_id,
                channel=ctx.channel,
                user_id=ctx.user_id,
            )
        except RuntimeError as exc:
            error = str(exc)
            if error.startswith("tool_blocked_by_safety_policy:exec:"):
                return f"skill_blocked:{spec_name}:{error}"
            raise

    @staticmethod
    def _exec_output_exit_code(payload: str) -> int | None:
        line = str(payload or "").splitlines()[0:1]
        if not line or not line[0].startswith("exit="):
            return None
        try:
            return int(line[0].split("=", 1)[1].strip())
        except ValueError:
            return None

    @staticmethod
    def _exec_output_stream(payload: str, key: str) -> str:
        prefix = f"{key}="
        for line in str(payload or "").splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
        return ""

    @staticmethod
    def _weather_code_description(code: int) -> str:
        mapping = {
            0: "clear sky",
            1: "mainly clear",
            2: "partly cloudy",
            3: "overcast",
            45: "fog",
            48: "rime fog",
            51: "light drizzle",
            53: "moderate drizzle",
            55: "dense drizzle",
            61: "slight rain",
            63: "moderate rain",
            65: "heavy rain",
            71: "slight snow",
            73: "moderate snow",
            75: "heavy snow",
            80: "rain showers",
            81: "strong rain showers",
            82: "violent rain showers",
            95: "thunderstorm",
        }
        return mapping.get(int(code), "unknown")

    async def _run_weather(self, arguments: dict[str, Any]) -> str:
        location = str(arguments.get("location") or arguments.get("input") or "").strip()
        if not location:
            location = "Sao Paulo"
        url = f"https://wttr.in/{quote_plus(location)}?format=3"
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(url)
                response.raise_for_status()
            return response.text.strip()
        except Exception:
            async with httpx.AsyncClient(timeout=12) as client:
                geocode = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1, "language": "en", "format": "json"},
                )
                geocode.raise_for_status()
                geocode_payload = geocode.json()
                results = geocode_payload.get("results", []) if isinstance(geocode_payload, dict) else []
                if not isinstance(results, list) or not results:
                    raise RuntimeError(f"weather_location_not_found:{location}")
                first = results[0] if isinstance(results[0], dict) else {}
                latitude = first.get("latitude")
                longitude = first.get("longitude")
                if latitude is None or longitude is None:
                    raise RuntimeError(f"weather_location_not_found:{location}")
                resolved_name = str(first.get("name", location) or location).strip()
                country = str(first.get("country", "") or "").strip()
                forecast = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "current_weather": "true",
                        "timezone": "auto",
                    },
                )
                forecast.raise_for_status()
            forecast_payload = forecast.json()
            current = forecast_payload.get("current_weather", {}) if isinstance(forecast_payload, dict) else {}
            if not isinstance(current, dict) or not current:
                raise RuntimeError("weather_current_unavailable")
            place = resolved_name if not country else f"{resolved_name}, {country}"
            return (
                f"{place}: {current.get('temperature')}°C, "
                f"{self._weather_code_description(int(current.get('weathercode', 0) or 0))}, "
                f"wind {current.get('windspeed')} km/h"
            )

    @staticmethod
    def _script_tool_arguments(script_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = arguments.get("tool_arguments")
        if isinstance(payload, dict):
            return payload

        if script_name == "web_search":
            query = str(arguments.get("query") or arguments.get("input") or "").strip()
            if not query:
                raise ValueError("query or input is required for web-search skill")
            limit = int(arguments.get("limit", 5) or 5)
            return {"query": query, "limit": limit}

        return {}

    async def _precheck_github_auth(self, *, spec_name: str, timeout: float, ctx: ToolContext) -> str | None:
        if os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN"):
            return None
        if self.registry.get("exec") is None:
            return None
        result = await self._run_command_via_exec_tool(
            spec_name=spec_name,
            argv=["gh", "auth", "status"],
            timeout=min(timeout, 15.0),
            ctx=ctx,
        )
        if result.startswith(f"skill_blocked:{spec_name}:"):
            return result
        exit_code = self._exec_output_exit_code(result)
        if exit_code is None or exit_code == 0:
            return None
        stderr = self._exec_output_stream(result, "stderr")
        detail = stderr or "gh auth status failed"
        return f"skill_auth_required:{spec_name}:gh:{detail}"

    async def _load_summary_source(self, arguments: dict[str, Any], ctx: ToolContext) -> tuple[str, str]:
        payload = arguments.get("tool_arguments")
        source_input = ""
        if isinstance(payload, dict):
            source_input = str(payload.get("input") or payload.get("url") or payload.get("path") or "").strip()
        if not source_input:
            source_input = str(arguments.get("input") or arguments.get("url") or arguments.get("path") or "").strip()
        if not source_input:
            extra = self._extra_args(arguments)
            source_input = extra[0] if extra else ""
        if not source_input:
            raise ValueError("input is required for summarize skill")

        if source_input.startswith(("http://", "https://")):
            if self.registry.get("web_fetch") is None:
                raise RuntimeError("summary_source_fetch_unavailable")
            raw = await self.registry.execute(
                "web_fetch",
                {"url": source_input, "max_chars": self.SUMMARY_MAX_SOURCE_CHARS},
                session_id=ctx.session_id,
                channel=ctx.channel,
                user_id=ctx.user_id,
            )
            decoded = json.loads(raw)
            if not decoded.get("ok"):
                message = decoded.get("error", {}).get("message", "web_fetch_failed")
                raise RuntimeError(f"summary_source_fetch_failed:{message}")
            result = decoded.get("result", {})
            return source_input, str(result.get("text", "") or "").strip()

        read_tool_name = "read" if self.registry.get("read") is not None else "read_file"
        if self.registry.get(read_tool_name) is None:
            raise RuntimeError("summary_source_reader_unavailable")
        text = await self.registry.execute(
            read_tool_name,
            {"path": source_input, "allow_large_file": True, "limit": self.SUMMARY_MAX_SOURCE_CHARS},
            session_id=ctx.session_id,
            channel=ctx.channel,
            user_id=ctx.user_id,
        )
        return source_input, str(text or "").strip()

    async def _run_summarize(self, arguments: dict[str, Any], ctx: ToolContext, *, spec_name: str, timeout: float) -> str:
        argv = ["summarize", *self._extra_args(arguments)]
        source_input = str(arguments.get("input") or arguments.get("url") or arguments.get("path") or "").strip()
        if len(argv) == 1 and source_input:
            argv.append(source_input)
        if shutil.which("summarize") is not None and self.registry.get("exec") is not None:
            result = await self._run_command_via_exec_tool(spec_name=spec_name, argv=argv, timeout=timeout, ctx=ctx)
            exit_code = self._exec_output_exit_code(result)
            if exit_code in {None, 0}:
                return result
        if self.provider is None:
            return f"skill_blocked:{spec_name}:provider_unavailable_for_summary"
        try:
            source_label, source_text = await self._load_summary_source(arguments, ctx)
        except (KeyError, RuntimeError, ValueError) as exc:
            reason = str(exc or "").strip() or "summary_source_reader_unavailable"
            if not reason.startswith("summary_source_"):
                reason = "summary_source_reader_unavailable"
            return f"skill_blocked:{spec_name}:{reason}"
        if not source_text:
            return f"skill_blocked:{spec_name}:summary_source_empty"
        response = await self.provider.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are ClawLite summarizing content. Preserve hard facts, numbers, dates, deadlines, "
                        "owners, and unresolved risks. Be concise and specific."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Summarize this source.\nSource: {source_label}\n\n{source_text[:self.SUMMARY_MAX_SOURCE_CHARS]}",
                },
            ],
            tools=[],
            max_tokens=500,
            temperature=0.2,
        )
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            return f"skill_blocked:{spec_name}:provider_empty_summary"
        return text

    @staticmethod
    def _skill_config_path(arguments: dict[str, Any]) -> str:
        payload = arguments.get("tool_arguments")
        if isinstance(payload, dict):
            value = payload.get("config") or payload.get("config_path") or payload.get("configPath") or ""
            return str(value or "").strip()
        return str(arguments.get("config") or arguments.get("config_path") or arguments.get("configPath") or "").strip()

    @staticmethod
    def _skill_payload(arguments: dict[str, Any]) -> dict[str, Any]:
        payload = arguments.get("tool_arguments")
        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _load_module_from_path(module_name: str, path: Path) -> Any:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"module_load_failed:{path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    async def _run_healthcheck(self, arguments: dict[str, Any], *, timeout: float) -> str:
        from clawlite.cli.ops import diagnostics_snapshot, fetch_gateway_diagnostics
        from clawlite.config.loader import DEFAULT_CONFIG_PATH, load_config

        config_path = self._skill_config_path(arguments)
        cfg = load_config(config_path or None)
        resolved_config_path = str(Path(config_path).expanduser()) if config_path else str(DEFAULT_CONFIG_PATH)
        payload = diagnostics_snapshot(cfg, config_path=resolved_config_path, include_validation=True)
        args_payload = self._skill_payload(arguments)
        gateway_url = str(args_payload.get("gateway_url") or args_payload.get("gatewayUrl") or "").strip()
        token = str(args_payload.get("token") or "").strip()
        if gateway_url:
            payload["gateway_probe"] = await asyncio.to_thread(
                fetch_gateway_diagnostics,
                gateway_url=gateway_url,
                timeout=min(timeout, 10.0),
                token=token,
            )
        return json.dumps(payload, ensure_ascii=False)

    async def _run_model_usage(self, arguments: dict[str, Any]) -> str:
        payload = self._skill_payload(arguments)
        provider = str(payload.get("provider") or arguments.get("provider") or "codex").strip().lower() or "codex"
        mode = str(payload.get("mode") or arguments.get("mode") or "current").strip().lower() or "current"
        input_path = str(payload.get("input") or arguments.get("input") or "").strip() or None
        explicit_model = str(payload.get("model") or arguments.get("model") or "").strip() or None
        output_format = str(payload.get("format") or arguments.get("format") or "text").strip().lower() or "text"
        pretty = bool(payload.get("pretty", arguments.get("pretty", False)))
        days_raw = payload.get("days", arguments.get("days"))
        days = int(days_raw) if days_raw not in {"", None} else None
        if provider not in {"codex", "claude"}:
            raise ValueError("provider must be codex or claude")
        if mode not in {"current", "all"}:
            raise ValueError("mode must be current or all")
        if output_format not in {"text", "json"}:
            raise ValueError("format must be text or json")

        script_path = Path(__file__).resolve().parents[1] / "skills" / "model-usage" / "scripts" / "model_usage.py"
        module = self._load_module_from_path("clawlite_skill_model_usage_runtime", script_path)
        usage_payload = module.load_payload(input_path, provider)
        entries = module.parse_daily_entries(usage_payload)
        entries = module.filter_by_days(entries, days)

        if mode == "all":
            totals = module.aggregate_costs(entries)
            if output_format == "json":
                body = module.build_json_all(provider, totals)
                return json.dumps(body, ensure_ascii=False, indent=2 if pretty else None)
            return module.render_text_all(provider, totals)

        model = explicit_model
        latest_model_date = None
        if not model:
            model, latest_model_date = module.pick_current_model(entries)
        if not model:
            raise RuntimeError("model_usage_current_model_unavailable")
        totals = module.aggregate_costs(entries)
        total_cost = float(totals.get(model, 0.0))
        latest_cost_date, latest_cost = module.latest_day_cost(entries, model)
        if output_format == "json":
            body = module.build_json_current(
                provider,
                model,
                latest_model_date,
                total_cost,
                latest_cost,
                latest_cost_date,
                len(entries),
            )
            return json.dumps(body, ensure_ascii=False, indent=2 if pretty else None)
        return module.render_text_current(
            provider,
            model,
            latest_model_date,
            total_cost,
            latest_cost,
            latest_cost_date,
            len(entries),
        )

    async def _run_session_logs(self, arguments: dict[str, Any]) -> str:
        from clawlite.config.loader import load_config
        from clawlite.session.store import SessionStore

        payload = self._skill_payload(arguments)
        config_path = self._skill_config_path(arguments)
        cfg = load_config(config_path or None)
        sessions_root = Path(cfg.state_path).expanduser() / "sessions"
        sessions_root.mkdir(parents=True, exist_ok=True)
        session_id = str(payload.get("session_id") or payload.get("sessionId") or arguments.get("session_id") or arguments.get("sessionId") or "").strip()
        query = str(payload.get("query") or arguments.get("query") or "").strip().lower()
        role_filter = str(payload.get("role") or arguments.get("role") or "").strip().lower()
        channel_filter = str(payload.get("channel") or arguments.get("channel") or "").strip().lower()
        limit_raw = payload.get("limit", arguments.get("limit", 20))
        limit = max(1, min(200, int(limit_raw or 20)))

        def _iter_rows(path: Path) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                raw = line.strip()
                if not raw:
                    continue
                try:
                    decoded = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(decoded, dict):
                    continue
                rows.append(decoded)
            return rows

        def _resolve_session_path(raw_session_id: str) -> Path | None:
            store = SessionStore(root=sessions_root)
            candidate_names = [
                store._safe_session_id(raw_session_id),
                raw_session_id.replace(":", "_"),
                raw_session_id.replace(":", "-"),
            ]
            seen: set[str] = set()
            for candidate in candidate_names:
                clean = str(candidate or "").strip()
                if not clean or clean in seen:
                    continue
                seen.add(clean)
                path = sessions_root / f"{clean}.jsonl"
                if path.exists():
                    return path
            for path in sessions_root.glob("*.jsonl"):
                rows = _iter_rows(path)
                if any(str(row.get("session_id", "") or "").strip() == raw_session_id for row in rows):
                    return path
            return None

        def _matches(row: dict[str, Any]) -> bool:
            role = str(row.get("role", "")).strip().lower()
            content = str(row.get("content", "") or "")
            metadata = row.get("metadata", {})
            channel = str(metadata.get("channel", "") if isinstance(metadata, dict) else "").strip().lower()
            if role_filter and role != role_filter:
                return False
            if channel_filter and channel != channel_filter:
                return False
            if query and query not in content.lower():
                return False
            return True

        if session_id:
            path = _resolve_session_path(session_id)
            if path is None:
                return json.dumps({"status": "failed", "error": "session_not_found", "session_id": session_id}, ensure_ascii=False)
            rows = [row for row in _iter_rows(path) if _matches(row)]
            rows = rows[-limit:]
            role_counts: dict[str, int] = {}
            for row in rows:
                role = str(row.get("role", "")).strip().lower()
                if role:
                    role_counts[role] = role_counts.get(role, 0) + 1
            return json.dumps(
                {
                    "status": "ok",
                    "session_id": session_id,
                    "count": len(rows),
                    "role_counts": role_counts,
                    "messages": rows,
                },
                ensure_ascii=False,
            )

        session_rows: list[dict[str, Any]] = []
        for path in sorted(sessions_root.glob("*.jsonl"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
            rows = _iter_rows(path)
            resolved_session_id = str(path.stem)
            if rows:
                first_session_id = str(rows[0].get("session_id", "") or "").strip()
                if first_session_id:
                    resolved_session_id = first_session_id
            if query or role_filter or channel_filter:
                matched = [row for row in rows if _matches(row)]
                if not matched:
                    continue
                for row in matched[:limit]:
                    session_rows.append(
                        {
                            "session_id": resolved_session_id,
                            "ts": str(row.get("ts", "") or ""),
                            "role": str(row.get("role", "") or ""),
                            "content": str(row.get("content", "") or ""),
                            "metadata": row.get("metadata", {}) if isinstance(row.get("metadata", {}), dict) else {},
                        }
                    )
                    if len(session_rows) >= limit:
                        break
            else:
                preview = rows[-1] if rows else {}
                session_rows.append(
                    {
                        "session_id": resolved_session_id,
                        "message_count": len(rows),
                        "last_ts": str(preview.get("ts", "") or ""),
                        "last_role": str(preview.get("role", "") or ""),
                        "last_content": str(preview.get("content", "") or "")[:160],
                    }
                )
            if len(session_rows) >= limit:
                break
        return json.dumps({"status": "ok", "count": len(session_rows), "sessions": session_rows[:limit]}, ensure_ascii=False)

    async def _run_coding_agent(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        payload = self._skill_payload(arguments)
        task = str(payload.get("task") or arguments.get("task") or arguments.get("input") or "").strip()
        tasks = payload.get("tasks")
        target_tool = self.registry.get("sessions_spawn")
        if target_tool is None:
            return "skill_script_unavailable:coding_agent"
        if not task and not isinstance(tasks, list):
            return json.dumps(
                {
                    "status": "ok",
                    "mode": "guide",
                    "available_tools": ["sessions_spawn", "subagents", "session_status", "sessions_history", "process", "apply_patch"],
                    "message": "Provide task or tasks to delegate coding work.",
                },
                ensure_ascii=False,
            )

        call_arguments: dict[str, Any] = {}
        if isinstance(tasks, list) and tasks:
            call_arguments["tasks"] = [str(item) for item in tasks if str(item).strip()]
        elif task:
            call_arguments["task"] = task
        for key in ("session_id", "sessionId", "target_sessions", "targetSessions", "share_scope", "shareScope"):
            value = payload.get(key)
            if value not in {None, ""}:
                call_arguments[key] = value
        return await self.registry.execute(
            "sessions_spawn",
            call_arguments,
            session_id=ctx.session_id,
            channel=ctx.channel,
            user_id=ctx.user_id,
        )

    @staticmethod
    def _gh_value(payload: dict[str, Any], arguments: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key, arguments.get(key))
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _gh_label_values(payload: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
        raw = payload.get("labels", arguments.get("labels"))
        if raw is None:
            raw = payload.get("label", arguments.get("label"))
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        text = str(raw or "").strip()
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]

    @staticmethod
    def _gh_bool(payload: dict[str, Any], arguments: dict[str, Any], *keys: str) -> bool:
        for key in keys:
            if key in payload:
                return bool(payload.get(key))
            if key in arguments:
                return bool(arguments.get(key))
        return False

    async def _run_gh_issues(
        self,
        arguments: dict[str, Any],
        ctx: ToolContext,
        *,
        spec_name: str,
        timeout: float,
    ) -> str:
        if self.registry.get("exec") is None:
            return f"skill_blocked:{spec_name}:exec_tool_not_registered"

        payload = self._skill_payload(arguments)
        extra_args = self._extra_args(arguments)
        if extra_args:
            auth_error = await self._precheck_github_auth(spec_name=spec_name, timeout=timeout, ctx=ctx)
            if auth_error is not None:
                return auth_error
            return await self._run_command_via_exec_tool(
                spec_name=spec_name,
                argv=["gh", "issue", *extra_args],
                timeout=timeout,
                ctx=ctx,
            )

        action = self._gh_value(payload, arguments, "action").lower() or "guide"
        repo = self._gh_value(payload, arguments, "repo", "repository")
        issue_number = self._gh_value(payload, arguments, "issue", "issue_number", "number")
        title = self._gh_value(payload, arguments, "title")
        body = self._gh_value(payload, arguments, "body")
        state = self._gh_value(payload, arguments, "state")
        search = self._gh_value(payload, arguments, "search", "query")
        assignee = self._gh_value(payload, arguments, "assignee")
        labels = self._gh_label_values(payload, arguments)
        wants_comments = self._gh_bool(payload, arguments, "comments", "include_comments")

        if action == "guide":
            return json.dumps(
                {
                    "status": "ok",
                    "mode": "guide",
                    "skill": spec_name,
                    "backend": "gh issue",
                    "available_actions": ["list", "view", "comment", "create"],
                    "required_fields": {
                        "list": ["repo(optional)"],
                        "view": ["issue"],
                        "comment": ["issue", "body"],
                        "create": ["title"],
                    },
                    "examples": {
                        "list": {"tool_arguments": {"action": "list", "repo": "owner/repo", "state": "open", "limit": 10}},
                        "view": {"tool_arguments": {"action": "view", "repo": "owner/repo", "issue": 123, "comments": True}},
                        "comment": {"tool_arguments": {"action": "comment", "repo": "owner/repo", "issue": 123, "body": "Investigating this now."}},
                        "create": {"tool_arguments": {"action": "create", "repo": "owner/repo", "title": "Bug title", "body": "Steps to reproduce"}},
                    },
                },
                ensure_ascii=False,
            )

        argv = ["gh", "issue"]
        if action == "list":
            argv.append("list")
            if repo:
                argv.extend(["--repo", repo])
            if state:
                argv.extend(["--state", state])
            if search:
                argv.extend(["--search", search])
            if assignee:
                argv.extend(["--assignee", assignee])
            if labels:
                argv.extend(["--label", ",".join(labels)])
            limit_value = payload.get("limit", arguments.get("limit", 20))
            limit = max(1, min(100, int(limit_value or 20)))
            argv.extend(["--limit", str(limit)])
        elif action == "view":
            if not issue_number:
                raise ValueError("issue is required for gh-issues view")
            argv.extend(["view", issue_number])
            if repo:
                argv.extend(["--repo", repo])
            if wants_comments:
                argv.append("--comments")
        elif action == "comment":
            if not issue_number:
                raise ValueError("issue is required for gh-issues comment")
            if not body:
                raise ValueError("body is required for gh-issues comment")
            argv.extend(["comment", issue_number])
            if repo:
                argv.extend(["--repo", repo])
            argv.extend(["--body", body])
        elif action == "create":
            if not title:
                raise ValueError("title is required for gh-issues create")
            argv.append("create")
            if repo:
                argv.extend(["--repo", repo])
            argv.extend(["--title", title])
            if body:
                argv.extend(["--body", body])
            if assignee:
                argv.extend(["--assignee", assignee])
            if labels:
                argv.extend(["--label", ",".join(labels)])
        else:
            raise ValueError("action must be one of: guide, list, view, comment, create")

        auth_error = await self._precheck_github_auth(spec_name=spec_name, timeout=timeout, ctx=ctx)
        if auth_error is not None:
            return auth_error
        return await self._run_command_via_exec_tool(spec_name=spec_name, argv=argv, timeout=timeout, ctx=ctx)

    async def _dispatch_script(self, script_name: str, arguments: dict[str, Any], ctx: ToolContext, *, spec_name: str) -> str:
        if script_name == "weather":
            return await self._run_weather(arguments)
        if script_name == "summarize":
            return await self._run_summarize(arguments, ctx, spec_name=spec_name, timeout=self._timeout_value(arguments))
        if script_name == "healthcheck":
            return await self._run_healthcheck(arguments, timeout=self._timeout_value(arguments))
        if script_name == "model_usage":
            return await self._run_model_usage(arguments)
        if script_name == "session_logs":
            return await self._run_session_logs(arguments)
        if script_name == "coding_agent":
            return await self._run_coding_agent(arguments, ctx)
        if script_name == "gh_issues":
            return await self._run_gh_issues(arguments, ctx, spec_name=spec_name, timeout=self._timeout_value(arguments))

        target_tool = self.registry.get(script_name)
        if target_tool is not None and script_name != self.name:
            tool_arguments = self._script_tool_arguments(script_name, arguments)
            try:
                return await self.registry.execute(
                    script_name,
                    tool_arguments,
                    session_id=ctx.session_id,
                    channel=ctx.channel,
                    user_id=ctx.user_id,
                )
            except RuntimeError as exc:
                if str(exc).startswith(f"tool_blocked_by_safety_policy:{script_name}:"):
                    return f"skill_blocked:{spec_name}:{exc}"
                raise

        return f"skill_script_unavailable:{script_name}"

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        name = str(arguments.get("name", "")).strip()
        log = bind_event("tool.skill", session=ctx.session_id, tool=self.name)
        if not name:
            raise ValueError("skill name is required")

        spec = self.loader.get(name)
        if spec is None:
            raise ValueError(f"skill_not_found:{name}")
        if not spec.enabled:
            return f"skill_disabled:{spec.name}"
        if not spec.available:
            details = ", ".join([*spec.missing, *spec.contract_issues])
            return f"skill_unavailable:{spec.name}:{details}"

        extra_args = self._extra_args(arguments)
        args_guard_error = self._guard_extra_args(extra_args)
        if args_guard_error:
            return f"skill_blocked:{spec.name}:{args_guard_error}"

        allowed, reason = await self._memory_policy_allows(session_id=ctx.session_id)
        if not allowed:
            return f"skill_blocked:{spec.name}:memory_policy:{reason}"

        timeout = self._timeout_value(arguments)

        if spec.execution_kind == "command":
            argv = [*spec.execution_argv, *extra_args]
            if spec.execution_argv and spec.execution_argv[0] == "gh":
                auth_error = await self._precheck_github_auth(spec_name=spec.name, timeout=timeout, ctx=ctx)
                if auth_error is not None:
                    return auth_error
            log.info("running skill command skill={}", spec.name)
            if self.registry.get("exec") is not None:
                return await self._run_command_via_exec_tool(spec_name=spec.name, argv=argv, timeout=timeout, ctx=ctx)
            return f"skill_blocked:{spec.name}:exec_tool_not_registered"

        if spec.execution_kind == "script":
            log.info("running skill script skill={} script={}", spec.name, spec.execution_target)
            return await self._dispatch_script(spec.execution_target, arguments, ctx, spec_name=spec.name)

        if spec.execution_kind == "invalid":
            details = ", ".join(spec.contract_issues)
            return f"skill_invalid_contract:{spec.name}:{details}"

        return f"skill_not_executable:{spec.name}"
