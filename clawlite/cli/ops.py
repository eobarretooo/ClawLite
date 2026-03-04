from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx

from clawlite.config.schema import AppConfig
from clawlite.core.memory import MemoryStore
from clawlite.providers.registry import SPECS, detect_provider_name
from clawlite.workspace.loader import TEMPLATE_FILES


def _mask_secret(value: str, *, keep: int = 4) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return f"{'*' * max(3, len(token) - keep)}{token[-keep:]}"


def provider_validation(config: AppConfig) -> dict[str, Any]:
    model = str(config.agents.defaults.model or config.provider.model).strip() or config.provider.model
    provider_name = detect_provider_name(model)
    spec = next((row for row in SPECS if row.name == provider_name), None)
    selected = getattr(config.providers, provider_name, None)

    provider_api_key = str(getattr(selected, "api_key", "") or "")
    provider_api_base = str(getattr(selected, "api_base", "") or "")
    resolved_api_key = provider_api_key or str(config.provider.litellm_api_key or "")
    resolved_base_url = provider_api_base or str(config.provider.litellm_base_url or "")

    env_hits: dict[str, bool] = {}
    env_names: list[str] = []
    if spec is not None:
        env_names.extend(list(spec.key_envs))
    env_names.extend(["CLAWLITE_LITELLM_API_KEY", "CLAWLITE_API_KEY"])
    seen: set[str] = set()
    for env_name in env_names:
        if env_name in seen:
            continue
        seen.add(env_name)
        env_hits[env_name] = bool(os.getenv(env_name, "").strip())

    checks: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []

    oauth = bool(spec.is_oauth) if spec is not None else False
    checks.append({"name": "provider_detected", "status": "ok", "detail": provider_name})

    if oauth:
        checks.append(
            {
                "name": "oauth_mode",
                "status": "ok",
                "detail": "OAuth provider selected; key validation is skipped here.",
            }
        )
    else:
        has_key = bool(resolved_api_key) or any(env_hits.values())
        if has_key:
            checks.append(
                {
                    "name": "api_key",
                    "status": "ok",
                    "detail": "API key configured via config or environment.",
                }
            )
        else:
            errors.append(f"Missing API key for provider '{provider_name}'.")
            checks.append(
                {
                    "name": "api_key",
                    "status": "error",
                    "detail": "Set a provider key in config.providers or provider-specific environment variables.",
                }
            )

    if provider_name == "custom":
        if resolved_base_url:
            checks.append({"name": "base_url", "status": "ok", "detail": resolved_base_url})
        else:
            errors.append("Custom provider requires providers.custom.api_base.")
            checks.append(
                {
                    "name": "base_url",
                    "status": "error",
                    "detail": "Set providers.custom.api_base for custom/<model> routes.",
                }
            )
    else:
        if resolved_base_url:
            checks.append({"name": "base_url", "status": "ok", "detail": resolved_base_url})
        else:
            warnings.append("Provider base URL is empty; runtime may fail when provider requires explicit base URL.")
            checks.append(
                {
                    "name": "base_url",
                    "status": "warning",
                    "detail": "Base URL not configured; defaults depend on provider resolution.",
                }
            )

    return {
        "ok": not errors,
        "model": model,
        "provider": provider_name,
        "oauth": oauth,
        "api_key_masked": _mask_secret(resolved_api_key),
        "base_url": resolved_base_url,
        "env_key_present": env_hits,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }


def channels_validation(config: AppConfig) -> dict[str, Any]:
    channels = config.channels
    enabled_names = channels.enabled_names()

    issues: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []

    builtins: list[tuple[str, dict[str, Any], list[str], list[str]]] = [
        ("telegram", {"token": channels.telegram.token, "allow_from": channels.telegram.allow_from}, ["token"], ["allow_from"]),
        ("discord", {"token": channels.discord.token}, ["token"], []),
        ("slack", {"bot_token": channels.slack.bot_token, "app_token": channels.slack.app_token}, ["bot_token"], ["app_token"]),
        ("whatsapp", {"bridge_url": channels.whatsapp.bridge_url}, ["bridge_url"], []),
    ]

    for name, payload, required_fields, warning_fields in builtins:
        enabled = bool(getattr(channels, name).enabled)
        record = {
            "channel": name,
            "enabled": enabled,
            "status": "disabled",
            "missing": [],
            "warnings": [],
        }
        if enabled:
            missing = [field for field in required_fields if not str(payload.get(field, "") or "").strip()]
            warns = [field for field in warning_fields if not payload.get(field)]
            if missing:
                record["status"] = "error"
                record["missing"] = missing
                issues.append(
                    {
                        "severity": "error",
                        "channel": name,
                        "detail": f"Missing required field(s): {', '.join(missing)}",
                    }
                )
            elif warns:
                record["status"] = "warning"
                record["warnings"] = warns
                issues.append(
                    {
                        "severity": "warning",
                        "channel": name,
                        "detail": f"Recommended field(s) not configured: {', '.join(warns)}",
                    }
                )
            else:
                record["status"] = "ok"
        rows.append(record)

    for name, payload in sorted(channels.extra.items()):
        enabled = bool(payload.get("enabled", False))
        record = {
            "channel": name,
            "enabled": enabled,
            "status": "disabled",
            "missing": [],
            "warnings": [],
        }
        if enabled:
            record["status"] = "warning"
            record["warnings"] = ["custom_channel_validation_not_available"]
            issues.append(
                {
                    "severity": "warning",
                    "channel": name,
                    "detail": "Enabled custom channel has no static validation rules.",
                }
            )
        rows.append(record)

    if not enabled_names:
        issues.append(
            {
                "severity": "warning",
                "channel": "*",
                "detail": "No channels are enabled; outbound operator alerts cannot be delivered.",
            }
        )

    errors = [item for item in issues if item["severity"] == "error"]
    return {
        "ok": not errors,
        "enabled": enabled_names,
        "channels": rows,
        "issues": issues,
    }


def onboarding_validation(config: AppConfig, *, fix: bool = False) -> dict[str, Any]:
    workspace = Path(config.workspace_path).expanduser()
    existing = [name for name in TEMPLATE_FILES if (workspace / name).exists()]
    missing = [name for name in TEMPLATE_FILES if (workspace / name) not in [(workspace / row) for row in existing]]

    created: list[str] = []
    if fix and missing:
        from clawlite.workspace.loader import WorkspaceLoader

        loader = WorkspaceLoader(workspace_path=workspace)
        generated = loader.bootstrap(overwrite=False)
        created = [str(path.relative_to(workspace)) for path in generated if path.exists()]
        existing = [name for name in TEMPLATE_FILES if (workspace / name).exists()]
        missing = [name for name in TEMPLATE_FILES if (workspace / name) not in [(workspace / row) for row in existing]]

    return {
        "ok": not missing,
        "workspace": str(workspace),
        "existing": existing,
        "missing": missing,
        "created": created,
    }


def diagnostics_snapshot(config: AppConfig, *, config_path: str, include_validation: bool = True) -> dict[str, Any]:
    state_path = Path(config.state_path).expanduser()
    cron_store = state_path / "cron_jobs.json"
    heartbeat_state = Path(config.workspace_path).expanduser() / "memory" / "heartbeat-state.json"
    payload: dict[str, Any] = {
        "config_path": config_path,
        "workspace_path": config.workspace_path,
        "state_path": config.state_path,
        "provider_model": config.agents.defaults.model,
        "memory_window": config.agents.defaults.memory_window,
        "session_retention_messages": config.agents.defaults.session_retention_messages,
        "agent_defaults": {
            "provider_model": config.agents.defaults.model,
            "memory_window": config.agents.defaults.memory_window,
            "session_retention_messages": config.agents.defaults.session_retention_messages,
        },
        "gateway": {
            "host": config.gateway.host,
            "port": config.gateway.port,
            "auth_mode": config.gateway.auth.mode,
            "diagnostics_enabled": config.gateway.diagnostics.enabled,
            "diagnostics_require_auth": config.gateway.diagnostics.require_auth,
        },
        "scheduler": {
            "heartbeat_interval_seconds": config.gateway.heartbeat.interval_s,
            "cron_store_exists": cron_store.exists(),
            "heartbeat_state_exists": heartbeat_state.exists(),
        },
        "channels_enabled": config.channels.enabled_names(),
    }
    if include_validation:
        payload["validation"] = {
            "provider": provider_validation(config),
            "channels": channels_validation(config),
            "onboarding": onboarding_validation(config, fix=False),
        }
    return payload


def fetch_gateway_diagnostics(*, gateway_url: str, timeout: float = 3.0, token: str = "") -> dict[str, Any]:
    base = gateway_url.strip().rstrip("/")
    if not base:
        raise RuntimeError("gateway_url_required")

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    out: dict[str, Any] = {"base_url": base, "endpoints": {}}
    client_timeout = max(0.1, float(timeout))
    with httpx.Client(timeout=client_timeout, headers=headers) as client:
        for endpoint in ("/health", "/v1/status", "/v1/diagnostics"):
            url = f"{base}{endpoint}"
            try:
                response = client.get(url)
                parsed: Any
                try:
                    parsed = response.json()
                except Exception:
                    parsed = response.text
                out["endpoints"][endpoint] = {
                    "status_code": response.status_code,
                    "ok": response.is_success,
                    "body": parsed,
                }
            except Exception as exc:
                out["endpoints"][endpoint] = {
                    "status_code": 0,
                    "ok": False,
                    "error": str(exc),
                }
    return out


def memory_eval_snapshot(config: AppConfig, limit: int = 5) -> dict[str, Any]:
    del config
    top_k = max(1, int(limit or 1))
    corpus: list[dict[str, str]] = [
        {
            "id": "mem_tz_001",
            "text": "User timezone is America/Sao_Paulo and prefers morning updates.",
            "source": "seed:profile",
            "created_at": "2026-03-01T08:00:00+00:00",
        },
        {
            "id": "mem_deploy_001",
            "text": "Deployment schedule is Friday at 17:00 UTC for production.",
            "source": "seed:ops",
            "created_at": "2026-03-01T09:00:00+00:00",
        },
        {
            "id": "mem_stack_001",
            "text": "Project stack uses Python FastAPI pytest and uvicorn.",
            "source": "seed:project",
            "created_at": "2026-03-01T10:00:00+00:00",
        },
        {
            "id": "mem_food_001",
            "text": "Remember grocery list includes banana bread coffee and eggs.",
            "source": "seed:personal",
            "created_at": "2026-03-01T11:00:00+00:00",
        },
        {
            "id": "mem_lang_001",
            "text": "User prefers Portuguese answers for operational updates.",
            "source": "seed:profile",
            "created_at": "2026-03-01T12:00:00+00:00",
        },
    ]
    cases: list[dict[str, Any]] = [
        {
            "name": "timezone_preference",
            "query": "what is my timezone preference",
            "expected_ids": ["mem_tz_001"],
        },
        {
            "name": "deployment_schedule",
            "query": "when do we deploy on friday",
            "expected_ids": ["mem_deploy_001"],
        },
        {
            "name": "project_stack",
            "query": "what stack do we use for project",
            "expected_ids": ["mem_stack_001"],
        },
        {
            "name": "grocery_memory",
            "query": "remember grocery list",
            "expected_ids": ["mem_food_001"],
        },
        {
            "name": "language_preference",
            "query": "what language do i prefer",
            "expected_ids": ["mem_lang_001"],
        },
    ]

    with tempfile.TemporaryDirectory(prefix="clawlite-memory-eval-") as temp_dir:
        base = Path(temp_dir)
        history_path = base / "memory.jsonl"
        curated_path = base / "memory_curated.json"
        checkpoints_path = base / "memory_checkpoints.json"
        store = MemoryStore(
            db_path=history_path,
            curated_path=curated_path,
            checkpoints_path=checkpoints_path,
        )
        history_lines = [
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in corpus
        ]
        history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")

        details: list[dict[str, Any]] = []
        passed = 0
        for case in cases:
            rows = store.search(str(case["query"]), limit=top_k)
            top_ids = [str(row.id) for row in rows[:top_k]]
            expected_ids = [str(item) for item in list(case["expected_ids"])]
            hit = bool(set(top_ids).intersection(expected_ids))
            if hit:
                passed += 1
            details.append(
                {
                    "name": str(case["name"]),
                    "query": str(case["query"]),
                    "expected_ids": expected_ids,
                    "top_ids": top_ids,
                    "hit": hit,
                }
            )

    total_cases = len(cases)
    failed = total_cases - passed
    return {
        "ok": failed == 0,
        "cases": total_cases,
        "passed": passed,
        "failed": failed,
        "details": details,
    }


def _file_stat(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "size_bytes": 0,
            "mtime": "",
        }
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return {
        "exists": True,
        "size_bytes": int(stat.st_size),
        "mtime": mtime,
    }


def _schema_hints(path: Path, *, kind: str) -> dict[str, Any]:
    hints: dict[str, Any] = {
        "exists": path.exists(),
        "version": None,
        "keys_present": [],
    }
    if not path.exists():
        return hints
    try:
        payload = json.loads(path.read_text(encoding="utf-8").strip() or "{}")
    except Exception:
        hints["parse_error"] = True
        return hints

    if isinstance(payload, dict):
        keys = sorted(str(key) for key in payload.keys())
        hints["keys_present"] = keys
        raw_version = payload.get("version")
        if isinstance(raw_version, (int, float, str)):
            hints["version"] = raw_version
        if kind == "checkpoints":
            hints["shape"] = "v2" if any(
                key in payload for key in ("source_signatures", "source_activity", "global_signatures")
            ) else "legacy_or_custom"
    else:
        hints["parse_error"] = True
    return hints


def memory_doctor_snapshot(config: AppConfig, repair: bool = False) -> dict[str, Any]:
    state_path = Path(config.state_path).expanduser()
    history_path = state_path / "memory.jsonl"
    curated_path = state_path / "memory_curated.json"
    checkpoints_path = state_path / "memory_checkpoints.json"

    payload: dict[str, Any] = {
        "ok": True,
        "repair_applied": False,
        "paths": {
            "history": str(history_path),
            "curated": str(curated_path),
            "checkpoints": str(checkpoints_path),
        },
        "files": {
            "history": _file_stat(history_path),
            "curated": _file_stat(curated_path),
            "checkpoints": _file_stat(checkpoints_path),
        },
        "counts": {"history": 0, "curated": 0, "total": 0},
        "analysis": {
            "recent": {"last_24h": 0, "last_7d": 0, "last_30d": 0},
            "temporal_marked_count": 0,
            "top_sources": [],
        },
        "diagnostics": {},
        "schema": {
            "curated": _schema_hints(curated_path, kind="curated"),
            "checkpoints": _schema_hints(checkpoints_path, kind="checkpoints"),
        },
    }

    try:
        store = MemoryStore(
            db_path=history_path,
            curated_path=curated_path,
            checkpoints_path=checkpoints_path,
        )
        if repair:
            store.all()
            payload["repair_applied"] = True
        stats = store.analysis_stats()
        payload["counts"] = dict(stats.get("counts", {}))
        payload["analysis"] = {
            "recent": dict(stats.get("recent", {})),
            "temporal_marked_count": int(stats.get("temporal_marked_count", 0) or 0),
            "top_sources": list(stats.get("top_sources", [])),
        }
        payload["diagnostics"] = store.diagnostics()
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
    return payload
