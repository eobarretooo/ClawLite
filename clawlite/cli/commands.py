from __future__ import annotations

import argparse
import asyncio
import sys
import webbrowser
from pathlib import Path
from typing import Any

from clawlite import __version__
from clawlite.cli.ops import channels_validation
from clawlite.cli.ops import diagnostics_snapshot
from clawlite.cli.ops import fetch_gateway_diagnostics
from clawlite.cli.ops import memory_eval_snapshot
from clawlite.cli.ops import memory_branch_checkout
from clawlite.cli.ops import memory_branch_create
from clawlite.cli.ops import memory_branches_snapshot
from clawlite.cli.ops import memory_export_snapshot
from clawlite.cli.ops import memory_import_snapshot
from clawlite.cli.ops import memory_merge_branches
from clawlite.cli.ops import memory_overview_snapshot
from clawlite.cli.ops import memory_quality_snapshot
from clawlite.cli.ops import memory_privacy_snapshot
from clawlite.cli.ops import memory_profile_snapshot
from clawlite.cli.ops import memory_shared_opt_in
from clawlite.cli.ops import memory_snapshot_create
from clawlite.cli.ops import memory_snapshot_rollback
from clawlite.cli.ops import memory_suggest_snapshot
from clawlite.cli.ops import memory_version_snapshot
from clawlite.cli.ops import memory_doctor_snapshot
from clawlite.cli.ops import onboarding_validation
from clawlite.cli.ops import heartbeat_trigger
from clawlite.cli.ops import pairing_approve
from clawlite.cli.ops import pairing_list
from clawlite.cli.ops import pairing_reject
from clawlite.cli.ops import pairing_revoke
from clawlite.cli.ops import discord_refresh
from clawlite.cli.ops import discord_status
from clawlite.cli.ops import telegram_offset_commit
from clawlite.cli.ops import telegram_offset_reset
from clawlite.cli.ops import telegram_offset_sync
from clawlite.cli.ops import telegram_refresh
from clawlite.cli.ops import telegram_status
from clawlite.cli.ops import provider_clear_auth
from clawlite.cli.ops import provider_live_probe
from clawlite.cli.ops import provider_recover
from clawlite.cli.ops import supervisor_recover
from clawlite.cli.ops import autonomy_wake
from clawlite.cli.ops import provider_validation
from clawlite.cli.ops import provider_login_openai_codex
from clawlite.cli.ops import provider_set_auth
from clawlite.cli.ops import provider_logout_openai_codex
from clawlite.cli.ops import provider_status
from clawlite.cli.ops import provider_use_model
from clawlite.cli.ops import telegram_live_probe
from clawlite.cli.onboarding import build_dashboard_handoff
from clawlite.cli.onboarding import run_onboarding_wizard
from clawlite.cli.onboarding import _run_configure_flow as run_configure_flow
from clawlite.config.loader import load_config
from clawlite.config.loader import DEFAULT_CONFIG_PATH
from clawlite.config.loader import save_config
from clawlite.core.skills import SkillsLoader
from clawlite.scheduler.cron import CronService
from clawlite.utils.logger import stdout_json
from clawlite.utils.logger import stdout_text
from clawlite.workspace.loader import WorkspaceLoader


def _print_json(payload: dict[str, Any]) -> None:
    stdout_json(payload)


def _print_stderr(text: str) -> None:
    sys.stderr.write(f"{text}\n")


def _format_cli_error(exc: BaseException) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    hint = ""
    lowered = message.lower()

    if "pyyaml is required for yaml config files" in lowered or (
        isinstance(exc, ModuleNotFoundError) and str(getattr(exc, "name", "") or "").strip().lower() == "yaml"
    ):
        hint = "install PyYAML or switch the config file to JSON: python -m pip install pyyaml"
    elif "playwright" in lowered and (
        "executable doesn't exist" in lowered or "looks like playwright was just installed" in lowered
    ):
        hint = "install the browser runtime once: python -m playwright install chromium"

    if hint:
        return f"error: {message}\nhint: {hint}"
    return f"error: {message}"


def _ensure_config_materialized(config_path: str | None) -> Any:
    target = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    existed = target.exists()
    cfg = load_config(config_path)
    if not existed:
        save_config(cfg, path=target)
        if config_path:
            stdout_text(f"Config criado em {target}.")
        else:
            stdout_text("Config criado em ~/.clawlite/config.json.")
    return cfg


def _parse_bool_flag(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected boolean value: true|false")


def _skills_loader_for_args(args: argparse.Namespace) -> SkillsLoader:
    config_path = getattr(args, "config", None)
    if config_path:
        cfg = load_config(config_path)
        return SkillsLoader(state_path=Path(cfg.state_path) / "skills-state.json")
    return SkillsLoader()


def cmd_start(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import run_gateway

    cfg = _ensure_config_materialized(args.config)
    host = args.host or cfg.gateway.host
    port = args.port or cfg.gateway.port
    run_gateway(host=host, port=port, config=cfg, config_path=args.config)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    config_path = str(args.config) if args.config else str(DEFAULT_CONFIG_PATH)
    channels_enabled = cfg.channels.enabled_names()
    workspace = WorkspaceLoader(workspace_path=cfg.workspace_path)
    bootstrap = workspace.bootstrap_status()
    cron = CronService(store_path=f"{cfg.state_path}/cron_jobs.json")
    jobs_count = len(cron.list_jobs())
    _print_json(
        {
            "config_path": config_path,
            "workspace_path": cfg.workspace_path,
            "provider_model": cfg.agents.defaults.model,
            "memory_window": cfg.agents.defaults.memory_window,
            "session_retention_messages": cfg.agents.defaults.session_retention_messages,
            "channels_enabled": channels_enabled,
            "cron_jobs_count": jobs_count,
            "heartbeat_interval_seconds": cfg.gateway.heartbeat.interval_s,
            "gateway_auth_mode": cfg.gateway.auth.mode,
            "gateway_auth_token_configured": bool(cfg.gateway.auth.token),
            "gateway_diagnostics_enabled": cfg.gateway.diagnostics.enabled,
            "bootstrap_pending": bool(bootstrap.get("pending", False)),
            "bootstrap_last_status": str(bootstrap.get("last_status", "") or ""),
        }
    )
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    cfg = _ensure_config_materialized(args.config)
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    handoff = build_dashboard_handoff(
        cfg,
        config_path=config_path,
        ensure_token=bool(cfg.gateway.auth.mode != "off"),
    )
    open_target = str(handoff["dashboard_url_with_token"] or handoff["gateway_url"])
    open_attempted = not bool(getattr(args, "no_open", False))
    opened = False
    open_error = ""
    if open_attempted and open_target:
        try:
            opened = bool(webbrowser.open(open_target))
        except Exception as exc:
            open_error = str(exc)
    _print_json(
        {
            "ok": True,
            "gateway_url": handoff["gateway_url"],
            "dashboard_url_with_token": handoff["dashboard_url_with_token"],
            "gateway_token_masked": handoff["gateway_token_masked"],
            "bootstrap_pending": handoff["bootstrap_pending"],
            "recommended_first_message": handoff["recommended_first_message"],
            "hatch_session_id": handoff["hatch_session_id"],
            "guidance": handoff["guidance"],
            "onboarding": handoff["onboarding"],
            "open_attempted": open_attempted,
            "opened": opened,
            "open_target": open_target,
            "open_error": open_error,
        }
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    runtime = build_runtime(cfg)

    async def _scenario() -> None:
        try:
            out = await asyncio.wait_for(
                runtime.engine.run(session_id=args.session_id, user_text=args.prompt),
                timeout=max(1.0, float(args.timeout)),
            )
            _print_json({"text": out.text, "model": out.model})
        except asyncio.TimeoutError:
            _print_json(
                {
                    "text": "Run timed out before the model finished. Increase --timeout or verify provider latency.",
                    "model": "engine/fallback",
                    "timed_out": True,
                }
            )

    asyncio.run(_scenario())
    return 0


def cmd_hatch(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    handoff = build_dashboard_handoff(cfg, config_path=args.config, ensure_token=False)
    if not bool(handoff.get("bootstrap_pending", False)):
        _print_json(
            {
                "ok": True,
                "status": "skipped",
                "reason": "not_pending",
                "session_id": handoff.get("hatch_session_id", "hatch:operator"),
                "message": "",
            }
        )
        return 0

    runtime = build_runtime(cfg)
    session_id = str(handoff.get("hatch_session_id", "hatch:operator") or "hatch:operator")
    message = str(args.message or handoff.get("recommended_first_message", "") or "Wake up, my friend!").strip()

    async def _scenario() -> int:
        try:
            out = await asyncio.wait_for(
                runtime.engine.run(session_id=session_id, user_text=message),
                timeout=max(1.0, float(args.timeout)),
            )
        except asyncio.TimeoutError:
            _print_json(
                {
                    "ok": False,
                    "status": "error",
                    "reason": "timed_out",
                    "session_id": session_id,
                    "message": message,
                }
            )
            return 2

        model = str(getattr(out, "model", "") or "").strip()
        text = str(getattr(out, "text", "") or "")
        if not model or model.startswith("engine/"):
            error = f"bootstrap_hatch_unsatisfied:{model or 'unknown_model'}"
            runtime.workspace.record_bootstrap_result(status="error", session_id=session_id, error=error)
            _print_json(
                {
                    "ok": False,
                    "status": "error",
                    "reason": error,
                    "session_id": session_id,
                    "message": message,
                    "text": text,
                    "model": model,
                }
            )
            return 2

        completed = bool(runtime.workspace.complete_bootstrap())
        if not completed:
            runtime.workspace.record_bootstrap_result(
                status="error",
                session_id=session_id,
                error="complete_bootstrap_returned_false",
            )
            _print_json(
                {
                    "ok": False,
                    "status": "error",
                    "reason": "complete_bootstrap_returned_false",
                    "session_id": session_id,
                    "message": message,
                    "text": text,
                    "model": model,
                }
            )
            return 2

        runtime.workspace.record_bootstrap_result(status="completed", session_id=session_id)
        _print_json(
            {
                "ok": True,
                "status": "completed",
                "reason": "hatch_completed",
                "session_id": session_id,
                "message": message,
                "text": text,
                "model": model,
            }
        )
        return 0

    return int(asyncio.run(_scenario()) or 0)


def cmd_configure(args: argparse.Namespace) -> int:
    """Two-level interactive configuration wizard (Basic / Advanced)."""
    cfg = _ensure_config_materialized(args.config)
    flow = str(getattr(args, "flow", "") or "").strip()
    if flow:
        payload = run_onboarding_wizard(
            cfg,
            config_path=args.config,
            overwrite=False,
            flow=flow,
            variables={
                "assistant_name": "ClawLite",
                "assistant_emoji": "🦊",
                "assistant_creature": "fox",
                "assistant_vibe": "direct, pragmatic, autonomous",
                "assistant_backstory": "An autonomous personal assistant focused on execution.",
                "user_name": "Owner",
                "user_timezone": "UTC",
                "user_context": "Personal operations and software projects",
                "user_preferences": "Clear answers, direct actions, concise updates",
            },
        )
        _print_json(payload)
        return 0 if bool(payload.get("ok", False)) else 2

    from rich.console import Console
    section = str(getattr(args, "section", None) or "").strip() or None
    payload = run_configure_flow(
        Console(),
        cfg,
        config_path=args.config,
        section=section,
    )
    _print_json(payload)
    return 0 if bool(payload.get("ok", False)) else 2



def cmd_onboard(args: argparse.Namespace) -> int:
    cfg = _ensure_config_materialized(args.config)
    if bool(getattr(args, "wizard", False)):
        payload = run_onboarding_wizard(
            cfg,
            config_path=args.config,
            overwrite=bool(args.overwrite),
            variables={
                "assistant_name": args.assistant_name,
                "assistant_emoji": args.assistant_emoji,
                "assistant_creature": args.assistant_creature,
                "assistant_vibe": args.assistant_vibe,
                "assistant_backstory": args.assistant_backstory,
                "user_name": args.user_name,
                "user_timezone": args.user_timezone,
                "user_context": args.user_context,
                "user_preferences": args.user_preferences,
            },
            flow=getattr(args, "flow", None),
        )
        _print_json(payload)
        return 0 if bool(payload.get("ok", False)) else 2

    loader = WorkspaceLoader(workspace_path=cfg.workspace_path)
    created = loader.bootstrap(
        overwrite=args.overwrite,
        variables={
            "assistant_name": args.assistant_name,
            "assistant_emoji": args.assistant_emoji,
            "assistant_creature": args.assistant_creature,
            "assistant_vibe": args.assistant_vibe,
            "assistant_backstory": args.assistant_backstory,
            "user_name": args.user_name,
            "user_timezone": args.user_timezone,
            "user_context": args.user_context,
            "user_preferences": args.user_preferences,
        },
    )
    _print_json({"workspace": cfg.workspace_path, "created_files": [str(path) for path in created]})
    return 0


def cmd_validate_provider(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = provider_validation(cfg)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_provider_login(args: argparse.Namespace) -> int:
    provider = str(args.provider).strip().lower().replace("_", "-")
    if provider != "openai-codex":
        _print_json({"ok": False, "error": f"unsupported_provider:{provider}"})
        return 2
    cfg = load_config(args.config)
    payload = provider_login_openai_codex(
        cfg,
        config_path=args.config,
        access_token=str(args.access_token or ""),
        account_id=str(args.account_id or ""),
        set_model=bool(args.set_model),
        keep_model=bool(args.keep_model),
        interactive=not bool(args.no_interactive),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_provider_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = provider_status(cfg, provider=str(args.provider or "openai-codex"))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_provider_logout(args: argparse.Namespace) -> int:
    provider = str(args.provider or "openai-codex").strip().lower().replace("_", "-")
    if provider != "openai-codex":
        _print_json({"ok": False, "error": f"unsupported_provider:{provider}"})
        return 2
    cfg = load_config(args.config)
    payload = provider_logout_openai_codex(cfg, config_path=args.config)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_provider_use(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = provider_use_model(
        cfg,
        config_path=args.config,
        provider=str(args.provider or ""),
        model=str(args.model or ""),
        fallback_model=str(args.fallback_model or ""),
        clear_fallback=bool(args.clear_fallback),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def _parse_cli_headers(header_values: list[str]) -> tuple[dict[str, str], str]:
    parsed: dict[str, str] = {}
    for raw in header_values:
        item = str(raw or "").strip()
        if not item or "=" not in item:
            return {}, f"invalid_header_format:{item}"
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            return {}, f"invalid_header_format:{item}"
        parsed[key] = value
    return parsed, ""


def cmd_provider_set_auth(args: argparse.Namespace) -> int:
    headers, header_error = _parse_cli_headers(list(args.header or []))
    if header_error:
        _print_json({"ok": False, "error": header_error})
        return 2

    cfg = load_config(args.config)
    payload = provider_set_auth(
        cfg,
        config_path=args.config,
        provider=str(args.provider or ""),
        api_key=str(args.api_key or ""),
        api_base=str(args.api_base or ""),
        extra_headers=headers,
        clear_headers=bool(args.clear_headers),
        clear_api_base=bool(args.clear_api_base),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_provider_clear_auth(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = provider_clear_auth(
        cfg,
        config_path=args.config,
        provider=str(args.provider or ""),
        clear_api_base=bool(args.clear_api_base),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_provider_recover(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = provider_recover(
        cfg,
        role=str(args.role or ""),
        model=str(args.model or ""),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_supervisor_recover(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = supervisor_recover(
        cfg,
        component=str(args.component or ""),
        force=bool(args.force),
        reason=str(args.reason or "operator_recover"),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_autonomy_wake(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = autonomy_wake(
        cfg,
        kind=str(args.kind or "proactive"),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_heartbeat_trigger(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = heartbeat_trigger(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_pairing_list(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = pairing_list(cfg, channel=str(args.channel or ""))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_pairing_approve(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = pairing_approve(
        cfg,
        channel=str(args.channel or ""),
        code=str(args.code or ""),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_pairing_reject(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = pairing_reject(
        cfg,
        channel=str(args.channel or ""),
        code=str(args.code or ""),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_pairing_revoke(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = pairing_revoke(
        cfg,
        channel=str(args.channel or ""),
        entry=str(args.entry or ""),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_discord_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = discord_status(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_discord_refresh(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = discord_refresh(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_telegram_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = telegram_status(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_telegram_refresh(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = telegram_refresh(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_telegram_offset_commit(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = telegram_offset_commit(
        cfg,
        update_id=int(args.update_id),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_telegram_offset_sync(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = telegram_offset_sync(
        cfg,
        next_offset=int(args.next_offset),
        allow_reset=bool(args.allow_reset),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_telegram_offset_reset(args: argparse.Namespace) -> int:
    if not bool(args.yes):
        _print_json({"ok": False, "error": "confirmation_required", "hint": "rerun_with_yes"})
        return 2
    cfg = load_config(args.config)
    payload = telegram_offset_reset(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_validate_channels(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = channels_validation(cfg)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_validate_onboarding(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = onboarding_validation(cfg, fix=bool(args.fix))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_validate_config(args: argparse.Namespace) -> int:
    config_path = str(args.config) if args.config else str(DEFAULT_CONFIG_PATH)
    try:
        cfg = load_config(args.config, strict=True)
    except Exception as exc:
        _print_json(
            {
                "ok": False,
                "strict": True,
                "config_path": config_path,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        )
        return 2

    _print_json(
        {
            "ok": True,
            "strict": True,
            "config_path": config_path,
            "provider_model": cfg.agents.defaults.model,
        }
    )
    return 0


def _gateway_preflight_from_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    endpoints = payload.get("endpoints")
    endpoint_rows: dict[str, Any] = endpoints if isinstance(endpoints, dict) else {}
    required = ("/health", "/v1/status", "/v1/diagnostics")
    normalized: dict[str, dict[str, Any]] = {}
    all_ok = True
    for endpoint in required:
        row = endpoint_rows.get(endpoint, {}) if isinstance(endpoint_rows.get(endpoint, {}), dict) else {}
        status_code = int(row.get("status_code", 0) or 0)
        ok = bool(row.get("ok", False))
        error = str(row.get("error", "") or "")
        normalized[endpoint] = {
            "ok": ok,
            "status_code": status_code,
            "error": error,
        }
        if not ok:
            all_ok = False
    return {
        "enabled": True,
        "ok": all_ok,
        "base_url": str(payload.get("base_url", "") or ""),
        "endpoints": normalized,
    }


def cmd_validate_preflight(args: argparse.Namespace) -> int:
    config_path = str(args.config) if args.config else str(DEFAULT_CONFIG_PATH)
    strict_block: dict[str, Any]
    try:
        strict_cfg = load_config(args.config, strict=True)
        strict_block = {
            "ok": True,
            "strict": True,
            "config_path": config_path,
            "provider_model": str(strict_cfg.agents.defaults.model or strict_cfg.provider.model),
        }
    except Exception as exc:
        strict_block = {
            "ok": False,
            "strict": True,
            "config_path": config_path,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }

    cfg = load_config(args.config)
    local_checks = {
        "provider": provider_validation(cfg),
        "channels": channels_validation(cfg),
        "onboarding": onboarding_validation(cfg, fix=False),
    }

    gateway_check: dict[str, Any] = {"enabled": False, "ok": True}
    gateway_url = str(args.gateway_url or "").strip()
    if gateway_url:
        diagnostics = fetch_gateway_diagnostics(
            gateway_url=gateway_url,
            timeout=float(args.timeout),
            token=str(args.token or ""),
        )
        gateway_check = _gateway_preflight_from_diagnostics(diagnostics)

    provider_live_check: dict[str, Any] = {"enabled": bool(args.provider_live), "ok": True}
    if bool(args.provider_live):
        probe = provider_live_probe(cfg, timeout=float(args.timeout))
        provider_live_check = {
            "enabled": True,
            "ok": bool(probe.get("ok", False)),
            "provider": str(probe.get("provider", "") or ""),
            "provider_detected": str(probe.get("provider_detected", "") or ""),
            "family": str(probe.get("family", "") or ""),
            "model": str(probe.get("model", "") or ""),
            "recommended_model": str(probe.get("recommended_model", "") or ""),
            "recommended_models": list(probe.get("recommended_models", []) or []),
            "status_code": int(probe.get("status_code", 0) or 0),
            "error": str(probe.get("error", "") or ""),
            "error_detail": str(probe.get("error_detail", "") or ""),
            "error_class": str(probe.get("error_class", "") or ""),
            "base_url": str(probe.get("base_url", "") or ""),
            "base_url_source": str(probe.get("base_url_source", "") or ""),
            "default_base_url": str(probe.get("default_base_url", "") or ""),
            "endpoint": str(probe.get("endpoint", "") or ""),
            "transport": str(probe.get("transport", "") or ""),
            "probe_method": str(probe.get("probe_method", "") or ""),
            "api_key_masked": str(probe.get("api_key_masked", "") or ""),
            "api_key_source": str(probe.get("api_key_source", "") or ""),
            "key_envs": list(probe.get("key_envs", []) or []),
            "model_check": dict(probe.get("model_check", {}) or {}),
            "onboarding_hint": str(probe.get("onboarding_hint", "") or ""),
            "hints": list(probe.get("hints", []) or []),
        }

    telegram_live_check: dict[str, Any] = {"enabled": bool(args.telegram_live), "ok": True}
    if bool(args.telegram_live):
        probe = telegram_live_probe(cfg, timeout=float(args.timeout))
        telegram_live_check = {
            "enabled": True,
            "ok": bool(probe.get("ok", False)),
            "status_code": int(probe.get("status_code", 0) or 0),
            "error": str(probe.get("error", "") or ""),
            "endpoint": str(probe.get("endpoint", "") or ""),
            "token_masked": str(probe.get("token_masked", "") or ""),
        }

    enabled_blocks = [
        strict_block,
        local_checks["provider"],
        local_checks["channels"],
        local_checks["onboarding"],
    ]
    if gateway_check.get("enabled", False):
        enabled_blocks.append(gateway_check)
    if provider_live_check.get("enabled", False):
        enabled_blocks.append(provider_live_check)
    if telegram_live_check.get("enabled", False):
        enabled_blocks.append(telegram_live_check)

    ok = all(bool(block.get("ok", False)) for block in enabled_blocks)
    payload = {
        "ok": ok,
        "strict_config": strict_block,
        "local_checks": local_checks,
        "gateway_probe": gateway_check,
        "provider_live_probe": provider_live_check,
        "telegram_live_probe": telegram_live_check,
    }
    _print_json(payload)
    return 0 if ok else 2


def cmd_diagnostics(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    config_path = str(args.config) if args.config else str(DEFAULT_CONFIG_PATH)
    payload: dict[str, Any] = {
        "local": diagnostics_snapshot(
            cfg,
            config_path=config_path,
            include_validation=not bool(args.no_validation),
        )
    }
    if args.gateway_url:
        payload["gateway"] = fetch_gateway_diagnostics(
            gateway_url=args.gateway_url,
            timeout=float(args.timeout),
            token=str(args.token or ""),
        )
    _print_json(payload)
    return 0


def cmd_memory_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_doctor_snapshot(cfg, repair=bool(args.repair))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_overview(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_overview_snapshot(cfg)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_eval(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_eval_snapshot(cfg, limit=int(args.limit))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_quality(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_quality_snapshot(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
        limit=int(args.limit),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_profile(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_profile_snapshot(cfg)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_suggest(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_suggest_snapshot(cfg, refresh=not bool(args.no_refresh))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_snapshot(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_snapshot_create(cfg, tag=str(args.tag or ""))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_version(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_version_snapshot(cfg)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_rollback(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_snapshot_rollback(cfg, version_id=str(args.id or ""))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_privacy(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_privacy_snapshot(cfg)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_export(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_export_snapshot(cfg, out_path=str(args.out or ""))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_import(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_import_snapshot(cfg, file_path=str(args.file or ""))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_branches(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_branches_snapshot(cfg)
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_branch(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_branch_create(
        cfg,
        name=str(args.name or ""),
        from_version=str(getattr(args, "from_version", "") or ""),
        checkout=bool(getattr(args, "checkout", False)),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_checkout(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_branch_checkout(cfg, name=str(args.name or ""))
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_merge(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_merge_branches(
        cfg,
        source=str(args.source or ""),
        target=str(args.target or ""),
        tag=str(args.tag or "merge"),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_memory_share_optin(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = memory_shared_opt_in(
        cfg,
        user_id=str(args.user or ""),
        enabled=bool(args.enabled),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_cron_add(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    runtime = build_runtime(cfg)

    async def _scenario() -> None:
        job_id = await runtime.cron.add_job(
            session_id=args.session_id,
            expression=args.expression,
            prompt=args.prompt,
            name=args.name,
        )
        _print_json({"id": job_id})

    asyncio.run(_scenario())
    return 0


def cmd_cron_list(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    runtime = build_runtime(cfg)
    rows = runtime.cron.list_jobs(session_id=args.session_id)
    _print_json({"jobs": rows})
    return 0


def cmd_cron_remove(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    runtime = build_runtime(cfg)
    ok = runtime.cron.remove_job(args.job_id)
    _print_json({"ok": ok})
    return 0


def cmd_cron_enable(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    runtime = build_runtime(cfg)
    ok = runtime.cron.enable_job(args.job_id, enabled=True)
    _print_json({"ok": ok, "job_id": args.job_id, "enabled": True})
    return 0


def cmd_cron_disable(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    runtime = build_runtime(cfg)
    ok = runtime.cron.enable_job(args.job_id, enabled=False)
    _print_json({"ok": ok, "job_id": args.job_id, "enabled": False})
    return 0


def cmd_cron_run(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import build_runtime

    cfg = load_config(args.config)
    runtime = build_runtime(cfg)

    async def _scenario() -> None:
        try:
            text = await runtime.cron.run_job(
                args.job_id,
                on_job=lambda job: runtime.engine.run(session_id=job.session_id, user_text=job.payload.prompt),
                force=True,
            )
            if hasattr(text, "text"):
                _print_json({"ok": True, "job_id": args.job_id, "text": text.text})
            else:
                _print_json({"ok": True, "job_id": args.job_id, "text": text or ""})
        except KeyError:
            _print_json({"ok": False, "error": f"job_not_found:{args.job_id}"})
        except RuntimeError as exc:
            _print_json({"ok": False, "error": str(exc)})

    asyncio.run(_scenario())
    return 0


def cmd_jobs_list(args: argparse.Namespace) -> int:
    from clawlite.jobs.journal import JobJournal
    from pathlib import Path
    cfg = load_config(args.config)
    state_path = str(cfg.state_path)
    persist_path = str(getattr(getattr(cfg, "jobs", None), "persist_path", "") or "").strip()
    if not persist_path:
        persist_path = str(Path(state_path) / "jobs.db")
    journal = JobJournal(persist_path)
    try:
        journal.open()
        jobs = journal.load_all()
        rows = [{"id": j.id, "kind": j.kind, "status": j.status, "priority": j.priority,
                 "session_id": j.session_id, "created_at": j.created_at} for j in jobs[:50]]
        _print_json({"jobs": rows, "total": len(jobs)})
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
    finally:
        journal.close()
    return 0


def cmd_jobs_status(args: argparse.Namespace) -> int:
    from clawlite.jobs.journal import JobJournal
    from pathlib import Path
    cfg = load_config(args.config)
    state_path = str(cfg.state_path)
    persist_path = str(getattr(getattr(cfg, "jobs", None), "persist_path", "") or "").strip()
    if not persist_path:
        persist_path = str(Path(state_path) / "jobs.db")
    journal = JobJournal(persist_path)
    try:
        journal.open()
        jobs = {j.id: j for j in journal.load_all()}
        job = jobs.get(args.job_id)
        if job is None:
            _print_json({"ok": False, "error": f"job_not_found:{args.job_id}"})
        else:
            _print_json({"id": job.id, "kind": job.kind, "status": job.status,
                         "result": job.result[:500], "error": job.error[:200],
                         "created_at": job.created_at, "finished_at": job.finished_at})
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
    finally:
        journal.close()
    return 0


def cmd_jobs_cancel(args: argparse.Namespace) -> int:
    # Cancel requires the live runtime — just print a note if journal-only mode
    _print_json({"ok": False, "error": "cancel requires live runtime; use the API endpoint"})
    return 1


def cmd_skills_list(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    rows = loader.discover(include_unavailable=args.all)
    payload = {
        "skills": [
            {
                "name": row.name,
                "description": row.description,
                "always": row.always,
                "source": row.source,
                "available": row.available,
                "enabled": row.enabled,
                "pinned": row.pinned,
                "version": row.version,
                "missing": row.missing,
                "command": row.command,
                "script": row.script,
                "path": str(row.path),
            }
            for row in rows
        ]
    }
    _print_json(payload)
    return 0


def cmd_skills_show(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.get(args.name)
    if row is None:
        _print_json({"error": f"skill_not_found:{args.name}"})
        return 1
    _print_json(
        {
            "name": row.name,
            "description": row.description,
            "always": row.always,
            "source": row.source,
            "available": row.available,
            "enabled": row.enabled,
            "pinned": row.pinned,
            "version": row.version,
            "version_pin": row.version_pin,
            "fallback_hint": row.fallback_hint,
            "missing": row.missing,
            "command": row.command,
            "script": row.script,
            "homepage": row.homepage,
            "path": str(row.path),
            "metadata": row.metadata,
            "body": row.body,
        }
    )
    return 0


def cmd_skills_check(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    _print_json(loader.diagnostics_report())
    return 0


def _skills_lifecycle_payload(action: str, row: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "name": row.name,
        "enabled": row.enabled,
        "pinned": row.pinned,
        "version_pin": row.version_pin,
        "available": row.available,
        "version": row.version,
        "source": row.source,
        "path": str(row.path),
    }


def cmd_skills_enable(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.set_enabled(args.name, True)
    if row is None:
        _print_json({"ok": False, "error": f"skill_not_found:{args.name}"})
        return 1
    _print_json(_skills_lifecycle_payload("enable", row))
    return 0


def cmd_skills_disable(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.set_enabled(args.name, False)
    if row is None:
        _print_json({"ok": False, "error": f"skill_not_found:{args.name}"})
        return 1
    _print_json(_skills_lifecycle_payload("disable", row))
    return 0


def cmd_skills_pin(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.set_pinned(args.name, True)
    if row is None:
        _print_json({"ok": False, "error": f"skill_not_found:{args.name}"})
        return 1
    _print_json(_skills_lifecycle_payload("pin", row))
    return 0


def cmd_skills_unpin(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.set_pinned(args.name, False)
    if row is None:
        _print_json({"ok": False, "error": f"skill_not_found:{args.name}"})
        return 1
    _print_json(_skills_lifecycle_payload("unpin", row))
    return 0


def cmd_skills_pin_version(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.set_version_pin(args.name, args.version)
    if row is None:
        _print_json({"ok": False, "error": f"skill_not_found:{args.name}"})
        return 1
    _print_json(_skills_lifecycle_payload("pin_version", row))
    return 0


def cmd_skills_clear_version(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.clear_version_pin(args.name)
    if row is None:
        _print_json({"ok": False, "error": f"skill_not_found:{args.name}"})
        return 1
    _print_json(_skills_lifecycle_payload("clear_version", row))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawlite",
        description="ClawLite autonomous assistant CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--config", default=None, help="Path to config JSON/YAML")
    parser.add_argument("--version", action="store_true", help="Show ClawLite version")
    sub = parser.add_subparsers(dest="command", required=False)

    p_start = sub.add_parser("start", help="Start FastAPI gateway")
    p_start.add_argument("--host", default=None)
    p_start.add_argument("--port", type=int, default=None)
    p_start.set_defaults(handler=cmd_start)

    p_gateway = sub.add_parser("gateway", help="Alias of 'start' (start FastAPI gateway)")
    p_gateway.add_argument("--host", default=None)
    p_gateway.add_argument("--port", type=int, default=None)
    p_gateway.set_defaults(handler=cmd_start)

    p_run = sub.add_parser("run", help="Run one prompt through the agent engine")
    p_run.add_argument("prompt")
    p_run.add_argument("--session-id", default="cli:default")
    p_run.add_argument("--timeout", type=float, default=20.0, help="Max seconds to wait for a single run")
    p_run.set_defaults(handler=cmd_run)

    p_hatch = sub.add_parser("hatch", help="Run the dedicated first-run bootstrap hatch")
    p_hatch.add_argument("--message", default="", help="Override the default hatch message")
    p_hatch.add_argument("--timeout", type=float, default=60.0, help="Max seconds to wait for the hatch run")
    p_hatch.set_defaults(handler=cmd_hatch)

    p_status = sub.add_parser("status", help="Show runtime/config status summary")
    p_status.set_defaults(handler=cmd_status)

    p_dashboard = sub.add_parser("dashboard", help="Print or open the local dashboard URL")
    p_dashboard.add_argument("--no-open", action="store_true", help="Print dashboard URLs without opening a browser")
    p_dashboard.set_defaults(handler=cmd_dashboard)

    p_configure = sub.add_parser("configure", help="Interactive configuration wizard (Basic / Advanced settings)")
    p_configure.add_argument(
        "--flow",
        choices=["quickstart", "advanced"],
        help="Compatibility shortcut: route to onboarding wizard flow",
    )
    p_configure.add_argument(
        "--section", default=None,
        help="Jump to a specific section: provider, gateway, channels, workspace, memory, context_budget, jobs, bus, tool_safety, autonomy"
    )
    p_configure.set_defaults(handler=cmd_configure)

    p_onboard = sub.add_parser("onboard", help="Generate workspace identity templates")
    p_onboard.add_argument("--assistant-name", default="ClawLite")
    p_onboard.add_argument("--assistant-emoji", default="🦊")
    p_onboard.add_argument("--assistant-creature", default="fox")
    p_onboard.add_argument("--assistant-vibe", default="direct, pragmatic, autonomous")
    p_onboard.add_argument("--assistant-backstory", default="An autonomous personal assistant focused on execution.")
    p_onboard.add_argument("--user-name", default="Owner")
    p_onboard.add_argument("--user-timezone", default="UTC")
    p_onboard.add_argument("--user-context", default="Personal operations and software projects")
    p_onboard.add_argument("--user-preferences", default="Clear answers, direct actions, concise updates")
    p_onboard.add_argument("--overwrite", action="store_true")
    p_onboard.add_argument("--wizard", action="store_true", help="Run interactive onboarding wizard")
    p_onboard.add_argument("--flow", choices=["quickstart", "advanced"], help="Choose wizard flow explicitly")
    p_onboard.set_defaults(handler=cmd_onboard)

    p_validate = sub.add_parser("validate", help="Validate provider/channel/onboarding readiness")
    validate_sub = p_validate.add_subparsers(dest="validate_command", required=True)

    p_validate_provider = validate_sub.add_parser("provider", help="Validate active provider/model configuration")
    p_validate_provider.set_defaults(handler=cmd_validate_provider)

    p_validate_channels = validate_sub.add_parser("channels", help="Validate enabled channel configuration")
    p_validate_channels.set_defaults(handler=cmd_validate_channels)

    p_validate_onboarding = validate_sub.add_parser("onboarding", help="Validate workspace onboarding templates")
    p_validate_onboarding.add_argument("--fix", action="store_true", help="Generate missing workspace templates")
    p_validate_onboarding.set_defaults(handler=cmd_validate_onboarding)

    p_validate_config = validate_sub.add_parser("config", help="Validate config structure with strict key checks")
    p_validate_config.set_defaults(handler=cmd_validate_config)

    p_validate_preflight = validate_sub.add_parser("preflight", help="Run release-grade local and optional integration checks")
    p_validate_preflight.add_argument("--gateway-url", default="", help="Gateway base URL to probe, e.g. http://127.0.0.1:8787")
    p_validate_preflight.add_argument("--token", default="", help="Bearer token for protected gateway probes")
    p_validate_preflight.add_argument("--timeout", type=float, default=3.0, help="Probe timeout in seconds")
    p_validate_preflight.add_argument("--provider-live", action="store_true", help="Run live provider connectivity probe")
    p_validate_preflight.add_argument("--telegram-live", action="store_true", help="Run live Telegram token probe")
    p_validate_preflight.set_defaults(handler=cmd_validate_preflight)

    p_provider = sub.add_parser("provider", help="Provider auth lifecycle commands")
    provider_sub = p_provider.add_subparsers(dest="provider_command", required=True)

    p_provider_login = provider_sub.add_parser("login", help="Login and persist provider auth")
    p_provider_login.add_argument("provider", choices=["openai-codex"])
    p_provider_login.add_argument("--access-token", default="", help="Explicit Codex access token")
    p_provider_login.add_argument("--account-id", default="", help="Optional OpenAI account/org id")
    p_provider_login.add_argument(
        "--set-model",
        action="store_true",
        help="Deprecated compatibility flag; Codex login now sets the active model automatically.",
    )
    p_provider_login.add_argument(
        "--keep-model",
        action="store_true",
        help="Persist Codex auth without switching the active model.",
    )
    p_provider_login.add_argument("--no-interactive", action="store_true", help="Disable interactive OAuth fallback")
    p_provider_login.set_defaults(handler=cmd_provider_login)

    p_provider_status = provider_sub.add_parser("status", help="Show provider auth status")
    p_provider_status.add_argument("provider", nargs="?", default="openai-codex")
    p_provider_status.set_defaults(handler=cmd_provider_status)

    p_provider_logout = provider_sub.add_parser("logout", help="Clear provider auth from config")
    p_provider_logout.add_argument("provider", nargs="?", default="openai-codex", choices=["openai-codex"])
    p_provider_logout.set_defaults(handler=cmd_provider_logout)

    p_provider_use = provider_sub.add_parser("use", help="Switch active provider/model and persist config")
    p_provider_use.add_argument("provider")
    p_provider_use.add_argument("--model", required=True)
    p_provider_use.add_argument("--fallback-model", default="")
    p_provider_use.add_argument("--clear-fallback", action="store_true")
    p_provider_use.set_defaults(handler=cmd_provider_use)

    p_provider_set_auth = provider_sub.add_parser("set-auth", help="Set provider API-key auth and persist config")
    p_provider_set_auth.add_argument("provider")
    p_provider_set_auth.add_argument("--api-key", required=True)
    p_provider_set_auth.add_argument("--api-base", default="")
    p_provider_set_auth.add_argument("--header", action="append", default=[])
    p_provider_set_auth.add_argument("--clear-headers", action="store_true")
    p_provider_set_auth.add_argument("--clear-api-base", action="store_true")
    p_provider_set_auth.set_defaults(handler=cmd_provider_set_auth)

    p_provider_clear_auth = provider_sub.add_parser("clear-auth", help="Clear provider API-key auth and headers")
    p_provider_clear_auth.add_argument("provider")
    p_provider_clear_auth.add_argument("--clear-api-base", action="store_true")
    p_provider_clear_auth.set_defaults(handler=cmd_provider_clear_auth)

    p_provider_recover = provider_sub.add_parser("recover", help="Clear provider suppression/cooldown through the gateway")
    p_provider_recover.add_argument("--role", default="", help="Optional candidate role filter, e.g. primary or fallback")
    p_provider_recover.add_argument("--model", default="", help="Optional candidate model filter")
    p_provider_recover.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_provider_recover.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_provider_recover.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_provider_recover.set_defaults(handler=cmd_provider_recover)

    p_autonomy = sub.add_parser("autonomy", help="Autonomy operator control commands")
    autonomy_sub = p_autonomy.add_subparsers(dest="autonomy_command", required=True)

    p_autonomy_wake = autonomy_sub.add_parser("wake", help="Trigger an autonomy wake through the gateway")
    p_autonomy_wake.add_argument("--kind", choices=["proactive", "heartbeat"], default="proactive")
    p_autonomy_wake.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_autonomy_wake.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_autonomy_wake.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_autonomy_wake.set_defaults(handler=cmd_autonomy_wake)

    p_supervisor = sub.add_parser("supervisor", help="Supervisor operator control commands")
    supervisor_sub = p_supervisor.add_subparsers(dest="supervisor_command", required=True)

    p_supervisor_recover = supervisor_sub.add_parser("recover", help="Trigger runtime supervisor recovery via the gateway")
    p_supervisor_recover.add_argument("--component", default="", help="Optional component name to recover")
    p_supervisor_recover.add_argument("--no-force", dest="force", action="store_false", help="Respect cooldown and budget instead of forcing recovery")
    p_supervisor_recover.add_argument("--reason", default="operator_recover", help="Recovery reason label")
    p_supervisor_recover.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_supervisor_recover.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_supervisor_recover.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_supervisor_recover.set_defaults(handler=cmd_supervisor_recover, force=True)

    p_heartbeat = sub.add_parser("heartbeat", help="Heartbeat control commands")
    heartbeat_sub = p_heartbeat.add_subparsers(dest="heartbeat_command", required=True)

    p_heartbeat_trigger = heartbeat_sub.add_parser("trigger", help="Trigger heartbeat cycle via gateway control endpoint")
    p_heartbeat_trigger.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_heartbeat_trigger.add_argument("--token", default="", help="Bearer token for control endpoint")
    p_heartbeat_trigger.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_heartbeat_trigger.set_defaults(handler=cmd_heartbeat_trigger)

    p_pairing = sub.add_parser("pairing", help="Manage pending pairing requests")
    pairing_sub = p_pairing.add_subparsers(dest="pairing_command", required=True)

    p_pairing_list = pairing_sub.add_parser("list", help="List pending pairing requests for a channel")
    p_pairing_list.add_argument("channel")
    p_pairing_list.set_defaults(handler=cmd_pairing_list)

    p_pairing_approve = pairing_sub.add_parser("approve", help="Approve a pairing code for a channel")
    p_pairing_approve.add_argument("channel")
    p_pairing_approve.add_argument("code")
    p_pairing_approve.set_defaults(handler=cmd_pairing_approve)

    p_pairing_reject = pairing_sub.add_parser("reject", help="Reject a pairing code for a channel")
    p_pairing_reject.add_argument("channel")
    p_pairing_reject.add_argument("code")
    p_pairing_reject.set_defaults(handler=cmd_pairing_reject)

    p_pairing_revoke = pairing_sub.add_parser("revoke", help="Revoke an approved pairing entry for a channel")
    p_pairing_revoke.add_argument("channel")
    p_pairing_revoke.add_argument("entry")
    p_pairing_revoke.set_defaults(handler=cmd_pairing_revoke)

    p_discord = sub.add_parser("discord", help="Discord operator control commands")
    discord_sub = p_discord.add_subparsers(dest="discord_command", required=True)

    p_discord_status = discord_sub.add_parser("status", help="Fetch Discord runtime status from the gateway")
    p_discord_status.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_discord_status.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_discord_status.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_discord_status.set_defaults(handler=cmd_discord_status)

    p_discord_refresh = discord_sub.add_parser("refresh", help="Refresh Discord transport state via the gateway")
    p_discord_refresh.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_discord_refresh.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_discord_refresh.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_discord_refresh.set_defaults(handler=cmd_discord_refresh)

    p_telegram = sub.add_parser("telegram", help="Telegram operator control commands")
    telegram_sub = p_telegram.add_subparsers(dest="telegram_command", required=True)

    p_telegram_status = telegram_sub.add_parser("status", help="Fetch Telegram runtime status from the gateway")
    p_telegram_status.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_telegram_status.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_telegram_status.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_telegram_status.set_defaults(handler=cmd_telegram_status)

    p_telegram_refresh = telegram_sub.add_parser("refresh", help="Refresh Telegram transport state via the gateway")
    p_telegram_refresh.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_telegram_refresh.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_telegram_refresh.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_telegram_refresh.set_defaults(handler=cmd_telegram_refresh)

    p_telegram_offset_commit = telegram_sub.add_parser("offset-commit", help="Advance Telegram offset watermark via the gateway")
    p_telegram_offset_commit.add_argument("update_id", type=int)
    p_telegram_offset_commit.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_telegram_offset_commit.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_telegram_offset_commit.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_telegram_offset_commit.set_defaults(handler=cmd_telegram_offset_commit)

    p_telegram_offset_sync = telegram_sub.add_parser("offset-sync", help="Sync Telegram next_offset via the gateway")
    p_telegram_offset_sync.add_argument("next_offset", type=int)
    p_telegram_offset_sync.add_argument("--allow-reset", action="store_true", help="Allow resetting the Telegram offset when next_offset is 0")
    p_telegram_offset_sync.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_telegram_offset_sync.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_telegram_offset_sync.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_telegram_offset_sync.set_defaults(handler=cmd_telegram_offset_sync)

    p_telegram_offset_reset = telegram_sub.add_parser("offset-reset", help="Reset Telegram next_offset via the gateway")
    p_telegram_offset_reset.add_argument("--yes", action="store_true", help="Confirm that the Telegram next_offset should be reset to zero")
    p_telegram_offset_reset.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_telegram_offset_reset.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_telegram_offset_reset.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_telegram_offset_reset.set_defaults(handler=cmd_telegram_offset_reset)

    p_diagnostics = sub.add_parser("diagnostics", help="Operator diagnostics snapshot (local + optional gateway checks)")
    p_diagnostics.add_argument("--gateway-url", default="", help="Gateway base URL to probe, e.g. http://127.0.0.1:8787")
    p_diagnostics.add_argument("--token", default="", help="Bearer token for protected gateway diagnostics endpoints")
    p_diagnostics.add_argument("--timeout", type=float, default=3.0, help="Gateway probe timeout in seconds")
    p_diagnostics.add_argument("--no-validation", action="store_true", help="Skip local provider/channel/onboarding validations")
    p_diagnostics.set_defaults(handler=cmd_diagnostics)

    p_memory = sub.add_parser("memory", help="Memory inspection and maintenance")
    memory_sub = p_memory.add_subparsers(dest="memory_command", required=False)
    p_memory.set_defaults(handler=cmd_memory_overview)

    p_memory_doctor = memory_sub.add_parser("doctor", help="Emit memory diagnostics snapshot")
    p_memory_doctor.add_argument("--json", action="store_true", help="Emit JSON output (default)")
    p_memory_doctor.add_argument("--repair", action="store_true", help="Trigger safe history repair before reporting")
    p_memory_doctor.set_defaults(handler=cmd_memory_doctor)

    p_memory_eval = memory_sub.add_parser("eval", help="Run deterministic synthetic memory retrieval evaluation")
    p_memory_eval.add_argument("--limit", type=int, default=5, help="Top-k retrieval limit per synthetic query")
    p_memory_eval.set_defaults(handler=cmd_memory_eval)

    p_memory_quality = memory_sub.add_parser("quality", help="Compute and persist memory quality-state report")
    p_memory_quality.add_argument("--json", action="store_true", help="Emit JSON output (default)")
    p_memory_quality.add_argument("--limit", type=int, default=5, help="Top-k retrieval limit per synthetic query")
    p_memory_quality.add_argument("--gateway-url", default="", help="Optional gateway base URL for diagnostics probe")
    p_memory_quality.add_argument("--token", default="", help="Optional bearer token for gateway diagnostics probe")
    p_memory_quality.add_argument("--timeout", type=float, default=3.0, help="Gateway probe timeout in seconds")
    p_memory_quality.set_defaults(handler=cmd_memory_quality)

    p_memory_profile = memory_sub.add_parser("profile", help="Show memory profile snapshot")
    p_memory_profile.set_defaults(handler=cmd_memory_profile)

    p_memory_suggest = memory_sub.add_parser("suggest", help="Show proactive memory suggestions snapshot")
    p_memory_suggest.add_argument("--no-refresh", action="store_true", help="Read pending suggestions without running a scan")
    p_memory_suggest.set_defaults(handler=cmd_memory_suggest)

    p_memory_snapshot = memory_sub.add_parser("snapshot", help="Create memory snapshot version")
    p_memory_snapshot.add_argument("--tag", default="", help="Optional tag to append to snapshot id")
    p_memory_snapshot.set_defaults(handler=cmd_memory_snapshot)

    p_memory_version = memory_sub.add_parser("version", help="List available memory snapshot ids")
    p_memory_version.set_defaults(handler=cmd_memory_version)

    p_memory_rollback = memory_sub.add_parser("rollback", help="Rollback memory state to snapshot id")
    p_memory_rollback.add_argument("id")
    p_memory_rollback.set_defaults(handler=cmd_memory_rollback)

    p_memory_privacy = memory_sub.add_parser("privacy", help="Show memory privacy rules snapshot")
    p_memory_privacy.set_defaults(handler=cmd_memory_privacy)

    p_memory_export = memory_sub.add_parser("export", help="Export memory snapshot payload")
    p_memory_export.add_argument("--out", default="", help="Write export payload to file path")
    p_memory_export.set_defaults(handler=cmd_memory_export)

    p_memory_import = memory_sub.add_parser("import", help="Import memory payload from file path")
    p_memory_import.add_argument("file")
    p_memory_import.set_defaults(handler=cmd_memory_import)

    p_memory_branches = memory_sub.add_parser("branches", help="Show memory branch metadata")
    p_memory_branches.set_defaults(handler=cmd_memory_branches)

    p_memory_branch = memory_sub.add_parser("branch", help="Create memory branch")
    p_memory_branch.add_argument("name")
    p_memory_branch.add_argument("--from-version", default="", dest="from_version")
    p_memory_branch.add_argument("--checkout", action="store_true")
    p_memory_branch.set_defaults(handler=cmd_memory_branch)

    p_memory_checkout = memory_sub.add_parser("checkout", help="Switch active memory branch")
    p_memory_checkout.add_argument("name")
    p_memory_checkout.set_defaults(handler=cmd_memory_checkout)

    p_memory_merge = memory_sub.add_parser("merge", help="Merge source branch into target branch")
    p_memory_merge.add_argument("--source", required=True)
    p_memory_merge.add_argument("--target", required=True)
    p_memory_merge.add_argument("--tag", default="merge")
    p_memory_merge.set_defaults(handler=cmd_memory_merge)

    p_memory_share_optin = memory_sub.add_parser("share-optin", help="Enable or disable user shared-memory opt-in")
    p_memory_share_optin.add_argument("--user", required=True)
    p_memory_share_optin.add_argument("--enabled", type=_parse_bool_flag, required=True)
    p_memory_share_optin.set_defaults(handler=cmd_memory_share_optin)

    p_cron = sub.add_parser("cron", help="Manage scheduled jobs")
    cron_sub = p_cron.add_subparsers(dest="cron_command", required=True)

    p_cron_add = cron_sub.add_parser("add", help="Add cron job")
    p_cron_add.add_argument("--session-id", required=True)
    p_cron_add.add_argument(
        "--expression",
        required=True,
        help=(
            "Accepted patterns:\n"
            "  every 120 -> every 120 seconds\n"
            "  at 2026-03-02T20:00:00 -> one-time at datetime\n"
            "  0 9 * * * -> cron syntax (requires croniter)"
        ),
    )
    p_cron_add.add_argument("--prompt", required=True)
    p_cron_add.add_argument("--name", default="")
    p_cron_add.set_defaults(handler=cmd_cron_add)

    p_cron_list = cron_sub.add_parser("list", help="List jobs for a session")
    p_cron_list.add_argument("--session-id", required=True)
    p_cron_list.set_defaults(handler=cmd_cron_list)

    p_cron_remove = cron_sub.add_parser("remove", help="Remove job by id")
    p_cron_remove.add_argument("--job-id", required=True)
    p_cron_remove.set_defaults(handler=cmd_cron_remove)

    p_cron_enable = cron_sub.add_parser("enable", help="Enable job by id")
    p_cron_enable.add_argument("job_id")
    p_cron_enable.set_defaults(handler=cmd_cron_enable)

    p_cron_disable = cron_sub.add_parser("disable", help="Disable job by id")
    p_cron_disable.add_argument("job_id")
    p_cron_disable.set_defaults(handler=cmd_cron_disable)

    p_cron_run = cron_sub.add_parser("run", help="Run job immediately by id")
    p_cron_run.add_argument("job_id")
    p_cron_run.set_defaults(handler=cmd_cron_run)

    p_jobs = sub.add_parser("jobs", help="Inspect persisted background jobs")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_command", required=True)

    p_jobs_list = jobs_sub.add_parser("list", help="List jobs from the persistence store")
    p_jobs_list.set_defaults(handler=cmd_jobs_list)

    p_jobs_status = jobs_sub.add_parser("status", help="Show status of a job by id")
    p_jobs_status.add_argument("job_id")
    p_jobs_status.set_defaults(handler=cmd_jobs_status)

    p_jobs_cancel = jobs_sub.add_parser("cancel", help="Cancel a job (requires live runtime)")
    p_jobs_cancel.add_argument("job_id")
    p_jobs_cancel.set_defaults(handler=cmd_jobs_cancel)

    p_skills = sub.add_parser("skills", help="Inspect available skills")
    skills_sub = p_skills.add_subparsers(dest="skills_command", required=True)

    p_skills_list = skills_sub.add_parser("list", help="List skills")
    p_skills_list.add_argument("--all", action="store_true", help="Include unavailable skills")
    p_skills_list.set_defaults(handler=cmd_skills_list)

    p_skills_show = skills_sub.add_parser("show", help="Show one skill body + metadata")
    p_skills_show.add_argument("name")
    p_skills_show.set_defaults(handler=cmd_skills_show)

    p_skills_check = skills_sub.add_parser("check", help="Emit aggregated deterministic skills diagnostics")
    p_skills_check.set_defaults(handler=cmd_skills_check)

    p_skills_enable = skills_sub.add_parser("enable", help="Enable one skill in the local state")
    p_skills_enable.add_argument("name")
    p_skills_enable.set_defaults(handler=cmd_skills_enable)

    p_skills_disable = skills_sub.add_parser("disable", help="Disable one skill in the local state")
    p_skills_disable.add_argument("name")
    p_skills_disable.set_defaults(handler=cmd_skills_disable)

    p_skills_pin = skills_sub.add_parser("pin", help="Pin one skill in the local state")
    p_skills_pin.add_argument("name")
    p_skills_pin.set_defaults(handler=cmd_skills_pin)

    p_skills_unpin = skills_sub.add_parser("unpin", help="Unpin one skill in the local state")
    p_skills_unpin.add_argument("name")
    p_skills_unpin.set_defaults(handler=cmd_skills_unpin)

    p_skills_pin_version = skills_sub.add_parser("pin-version", help="Pin a skill to a specific version string")
    p_skills_pin_version.add_argument("name")
    p_skills_pin_version.add_argument("version")
    p_skills_pin_version.set_defaults(handler=cmd_skills_pin_version)

    p_skills_clear_version = skills_sub.add_parser("clear-version", help="Remove version pin for a skill")
    p_skills_clear_version.add_argument("name")
    p_skills_clear_version.set_defaults(handler=cmd_skills_clear_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(getattr(args, "version", False)):
        stdout_text(__version__)
        return 0
    handler = getattr(args, "handler", None)
    if not callable(handler):
        parser.print_help()
        return 1
    try:
        return int(handler(args) or 0)
    except KeyboardInterrupt:
        _print_stderr("error: interrupted")
        return 130
    except (ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
        _print_stderr(_format_cli_error(exc))
        return 2
