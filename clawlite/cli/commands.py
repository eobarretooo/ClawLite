from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from clawlite import __version__
from clawlite.cli.ops import channels_validation
from clawlite.cli.ops import diagnostics_snapshot
from clawlite.cli.ops import fetch_gateway_diagnostics
from clawlite.cli.ops import fetch_gateway_tool_approvals
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
from clawlite.cli.ops import skills_refresh
from clawlite.cli.ops import skills_validate
from clawlite.cli.ops import telegram_offset_commit
from clawlite.cli.ops import telegram_offset_reset
from clawlite.cli.ops import telegram_offset_sync
from clawlite.cli.ops import telegram_refresh
from clawlite.cli.ops import telegram_status
from clawlite.cli.ops import fetch_gateway_tools_catalog
from clawlite.cli.ops import provider_clear_auth
from clawlite.cli.ops import provider_live_probe
from clawlite.cli.ops import provider_recover
from clawlite.cli.ops import supervisor_recover
from clawlite.cli.ops import autonomy_wake
from clawlite.cli.ops import self_evolution_status
from clawlite.cli.ops import self_evolution_trigger
from clawlite.cli.ops import review_gateway_tool_approval
from clawlite.cli.ops import revoke_gateway_tool_grants
from clawlite.cli.ops import provider_validation
from clawlite.cli.ops import provider_login_oauth
from clawlite.cli.ops import provider_set_auth
from clawlite.cli.ops import provider_logout_oauth
from clawlite.cli.ops import provider_status
from clawlite.cli.ops import provider_use_model
from clawlite.cli.ops import resolve_oauth_provider_auth
from clawlite.cli.ops import _provider_spec
from clawlite.cli.ops import telegram_live_probe
from clawlite.cli.onboarding import build_dashboard_handoff
from clawlite.cli.onboarding import run_onboarding_wizard
from clawlite.cli.onboarding import _run_configure_flow as run_configure_flow
from clawlite.config.loader import config_payload_path
from clawlite.config.loader import load_config
from clawlite.config.loader import load_target_config_payload
from clawlite.config.loader import DEFAULT_CONFIG_PATH
from clawlite.config.loader import save_config
from clawlite.config.loader import save_raw_config_payload
from clawlite.config.schema import AppConfig
from clawlite.core.skills import SkillsLoader
from clawlite.core.skills import skills_doctor_hint
from clawlite.core.skills import skills_doctor_report
from clawlite.core.skills import skills_doctor_status
from clawlite.core.skills import skills_managed_report
from clawlite.core.skills import skills_sync_report
from clawlite.scheduler.cron import CronService
from clawlite.tools.registry import ToolRegistry
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


def _ensure_config_materialized(config_path: str | None, *, profile: str | None = None) -> Any:
    target = config_payload_path(config_path, profile=profile)
    existed = target.exists()
    cfg = load_config(config_path, profile=profile)
    if not existed:
        save_raw_config_payload(cfg.to_dict(), config_path, profile=profile)
        if config_path:
            stdout_text(f"Config criado em {target}.")
        else:
            stdout_text("Config criado em ~/.clawlite/config.json.")
    return cfg


@contextmanager
def _temporary_cli_profile(profile: str | None):
    if profile is None:
        yield
        return
    previous = os.environ.get("CLAWLITE_PROFILE")
    normalized = str(profile or "").strip()
    if normalized:
        os.environ["CLAWLITE_PROFILE"] = normalized
    else:
        os.environ.pop("CLAWLITE_PROFILE", None)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CLAWLITE_PROFILE", None)
        else:
            os.environ["CLAWLITE_PROFILE"] = previous


def _parse_bool_flag(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected boolean value: true|false")


def _skills_loader_for_args(args: argparse.Namespace) -> SkillsLoader:
    config_path = getattr(args, "config", None)
    config_profile = getattr(args, "profile", None)
    if config_path or config_profile:
        cfg = load_config(config_path, profile=config_profile)
        return SkillsLoader(
            state_path=Path(cfg.state_path) / "skills-state.json",
            config_path=config_path,
            config_profile=config_profile,
        )
    return SkillsLoader()


def _build_runtime_for_args(args: argparse.Namespace, cfg=None):
    from clawlite.gateway.server import build_runtime

    config_path = getattr(args, "config", None)
    config_profile = getattr(args, "profile", None)
    if config_path or config_profile:
        resolved_cfg = load_config(config_path, profile=config_profile)
    else:
        resolved_cfg = cfg if cfg is not None else load_config(None)
    return build_runtime(
        resolved_cfg,
        config_path=config_path,
        config_profile=config_profile,
    )


def _parse_skill_env_assignments(values: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in values:
        text = str(raw or "").strip()
        if not text or "=" not in text:
            raise ValueError("expected KEY=VALUE for --env")
        key, value = text.split("=", 1)
        env_key = str(key or "").strip()
        if not env_key:
            raise ValueError("expected KEY=VALUE for --env")
        env[env_key] = value
    return env


def _skills_managed_root(loader: SkillsLoader) -> Path:
    return loader.roots[2].parent


def _run_clawhub_command(loader: SkillsLoader, *action_args: str) -> tuple[int, dict[str, Any]]:
    managed_root = _skills_managed_root(loader)
    skills_root = managed_root / "skills"
    npx_path = shutil.which("npx")
    if not npx_path:
        return 1, {
            "ok": False,
            "error": "skills_manager_requires_npx",
            "managed_root": str(managed_root),
            "skills_root": str(skills_root),
        }

    managed_root.mkdir(parents=True, exist_ok=True)
    command = [npx_path, "--yes", "clawhub@latest", *action_args, "--workdir", str(managed_root)]
    completed = subprocess.run(command, capture_output=True, text=True)
    payload = {
        "ok": completed.returncode == 0,
        "command": command,
        "managed_root": str(managed_root),
        "skills_root": str(skills_root),
        "stdout": str(completed.stdout or "").strip(),
        "stderr": str(completed.stderr or "").strip(),
    }
    if completed.returncode != 0:
        payload["error"] = "skills_manager_command_failed"
    return completed.returncode, payload


def cmd_start(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import run_gateway

    cfg = _ensure_config_materialized(args.config, profile=getattr(args, "profile", None))
    host = args.host or cfg.gateway.host
    port = args.port or cfg.gateway.port
    run_gateway(host=host, port=port, config=cfg, config_path=args.config, config_profile=getattr(args, "profile", None))
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
    config_profile = getattr(args, "profile", None)
    cfg = _ensure_config_materialized(args.config, profile=config_profile)
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    handoff = build_dashboard_handoff(
        cfg,
        config_path=config_path,
        config_profile=config_profile,
        ensure_token=bool(cfg.gateway.auth.mode != "off"),
    )
    dashboard_handoff_url = str(handoff.get("dashboard_url_with_handoff") or handoff["dashboard_url_with_token"] or "")
    open_target = dashboard_handoff_url or str(handoff["gateway_url"])
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
            "dashboard_url_with_handoff": dashboard_handoff_url,
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
    cfg = load_config(args.config)
    runtime = _build_runtime_for_args(args, cfg)

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
        finally:
            drain_turn_persistence = getattr(runtime.engine, "drain_turn_persistence", None)
            if callable(drain_turn_persistence):
                await drain_turn_persistence()

    asyncio.run(_scenario())
    return 0


def cmd_hatch(args: argparse.Namespace) -> int:
    config_profile = getattr(args, "profile", None)
    cfg = load_config(args.config, profile=config_profile)
    handoff = build_dashboard_handoff(
        cfg,
        config_path=args.config,
        config_profile=config_profile,
        ensure_token=False,
    )
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

    runtime = _build_runtime_for_args(args, cfg)
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
        finally:
            drain_turn_persistence = getattr(runtime.engine, "drain_turn_persistence", None)
            if callable(drain_turn_persistence):
                await drain_turn_persistence()

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
    config_profile = getattr(args, "profile", None)
    cfg = _ensure_config_materialized(args.config, profile=config_profile)
    flow = str(getattr(args, "flow", "") or "").strip()
    if flow:
        payload = run_onboarding_wizard(
            cfg,
            config_path=args.config,
            config_profile=config_profile,
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
        config_profile=config_profile,
        section=section,
    )
    _print_json(payload)
    return 0 if bool(payload.get("ok", False)) else 2



def cmd_onboard(args: argparse.Namespace) -> int:
    config_profile = getattr(args, "profile", None)
    cfg = _ensure_config_materialized(args.config, profile=config_profile)
    if bool(getattr(args, "wizard", False)):
        payload = run_onboarding_wizard(
            cfg,
            config_path=args.config,
            config_profile=config_profile,
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
    cfg = load_config(args.config)
    payload = provider_login_oauth(
        cfg,
        config_path=args.config,
        provider=provider,
        access_token=str(args.access_token or ""),
        account_id=str(args.account_id or ""),
        set_model=bool(args.set_model),
        keep_model=bool(getattr(args, "keep_model", False)),
        interactive=not bool(getattr(args, "no_interactive", False)),
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
    cfg = load_config(args.config)
    payload = provider_logout_oauth(cfg, config_path=args.config, provider=provider)
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


def cmd_self_evolution_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = self_evolution_status(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_self_evolution_trigger(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = self_evolution_trigger(
        cfg,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
        dry_run=bool(getattr(args, "dry_run", False)),
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


def _trim_probe_output(value: Any, *, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _docker_compose_rows(raw: str) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            snippet = str(line or "").strip()
            if not snippet:
                continue
            try:
                row = json.loads(snippet)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _docker_compose_field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row.get(name)
        lowered = str(name or "").lower()
        if lowered in row:
            return row.get(lowered)
    return None


def _docker_service_summary(row: dict[str, Any]) -> dict[str, Any]:
    service = str(_docker_compose_field(row, "Service") or _docker_compose_field(row, "Name") or "").strip()
    state = str(_docker_compose_field(row, "State") or "").strip().lower()
    health = str(_docker_compose_field(row, "Health") or "").strip().lower()
    status = str(_docker_compose_field(row, "Status") or "").strip()
    lowered_status = status.lower()
    if not state:
        if lowered_status.startswith("up "):
            state = "running"
        elif lowered_status.startswith("exited"):
            state = "exited"
    running = state == "running"
    ok = running and health not in {"starting", "unhealthy"}
    return {
        "service": service,
        "running": running,
        "ok": ok,
        "state": state,
        "health": health,
        "status": status or ("not_running" if not state else state),
    }


def _docker_env_file_details(repo_root: Path) -> dict[str, Any]:
    raw = str(os.getenv("CLAWLITE_DOCKER_ENV_FILE", "") or "").strip()
    payload: dict[str, Any] = {
        "configured": bool(raw),
        "ok": True,
        "path": "",
        "error": "",
    }
    if not raw:
        return payload

    raw_path = Path(raw)
    candidates = [raw_path]
    if not raw_path.is_absolute():
        repo_candidate = repo_root / raw_path
        if repo_candidate not in candidates:
            candidates.append(repo_candidate)

    for candidate in candidates:
        if candidate.is_file():
            payload["path"] = str(candidate.resolve())
            return payload

    payload["ok"] = False
    payload["path"] = raw
    payload["error"] = "docker_env_file_missing"
    return payload


DOCKER_PROVIDER_FALLBACK_ENVS: tuple[str, ...] = (
    "CLAWLITE_LITELLM_API_KEY",
    "CLAWLITE_API_KEY",
)

DOCKER_OAUTH_ENV_GROUPS: dict[str, tuple[str, ...]] = {
    "openai_codex": (
        "CLAWLITE_CODEX_ACCESS_TOKEN",
        "OPENAI_CODEX_ACCESS_TOKEN",
        "OPENAI_ACCESS_TOKEN",
    ),
    "gemini_oauth": (
        "CLAWLITE_GEMINI_ACCESS_TOKEN",
        "GEMINI_ACCESS_TOKEN",
        "CLAWLITE_GEMINI_AUTH_PATH",
    ),
    "qwen_oauth": (
        "CLAWLITE_QWEN_ACCESS_TOKEN",
        "QWEN_ACCESS_TOKEN",
    ),
}


def _parse_docker_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    target = Path(str(path or "")).expanduser()
    if not target.is_file():
        return values
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = str(raw_line or "").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        env_name = str(key or "").strip()
        if not env_name:
            continue
        value = str(raw_value or "").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[env_name] = value
    return values


def _docker_effective_env_value(name: str, env_file_values: dict[str, str]) -> tuple[str, str]:
    env_name = str(name or "").strip()
    if not env_name:
        return "", ""
    shell_value = os.getenv(env_name, "").strip()
    if shell_value:
        return shell_value, "shell"
    env_file_value = str(env_file_values.get(env_name, "") or "").strip()
    if env_file_value:
        return env_file_value, "env_file"
    return "", ""


def _docker_secret_hint_target(env_file: dict[str, Any]) -> str:
    if bool(env_file.get("configured")) and str(env_file.get("path") or "").strip():
        return f"in CLAWLITE_DOCKER_ENV_FILE ({env_file['path']}) or the shell before docker compose up"
    return "in the shell before docker compose up or in CLAWLITE_DOCKER_ENV_FILE"


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _docker_visible_config(
    *,
    config_path: str | Path | None,
    config_profile: str | None,
) -> tuple[AppConfig | None, str]:
    target = config_payload_path(config_path, profile=config_profile)
    if not target.exists():
        return None, ""
    visible_root = DEFAULT_CONFIG_PATH.parent
    if not _path_is_within(target, visible_root):
        return None, ""
    raw_payload = load_target_config_payload(config_path, profile=config_profile)
    if not raw_payload:
        return None, str(target.resolve())
    return AppConfig.model_validate(raw_payload), str(target.resolve())


def _docker_secret_status(
    *,
    config: Any | None,
    config_path: str | Path | None,
    config_profile: str | None,
    provider_check: dict[str, Any] | None,
    env_file: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "error": "",
        "errors": [],
        "warnings": [],
        "hints": [],
        "provider": {
            "detected": "",
            "model": "",
            "auth_mode": "",
            "configured": False,
            "configured_source": "",
            "available_envs": [],
            "missing_envs": [],
        },
        "gateway_auth": {
            "mode": "",
            "token_configured": False,
            "token_source": "",
            "error": "",
        },
    }
    if config is None:
        return payload

    env_file_values = {}
    if bool(env_file.get("configured")) and bool(env_file.get("ok")):
        env_file_values = _parse_docker_env_file(str(env_file.get("path") or ""))
    visible_config, visible_config_path = _docker_visible_config(config_path=config_path, config_profile=config_profile)

    provider_payload = dict(provider_check or provider_validation(config) or {})
    provider_name = str(provider_payload.get("provider", "") or "")
    provider_model = str(provider_payload.get("model", "") or "")
    spec = _provider_spec(provider_name) if provider_name else None
    provider_auth_mode = "oauth" if bool(spec and getattr(spec, "is_oauth", False)) else (
        "none" if provider_name in {"ollama", "vllm"} else "api_key"
    )
    provider_configured = provider_auth_mode == "none"
    provider_source = ""
    provider_envs: list[str] = []
    if provider_auth_mode == "api_key":
        provider_envs.extend(str(name or "").strip() for name in list(getattr(spec, "key_envs", ()) or ()))
        provider_envs.extend(DOCKER_PROVIDER_FALLBACK_ENVS)
        if visible_config is not None:
            selected = visible_config.providers.get(provider_name) if provider_name else None
            cfg_api_key = str(getattr(selected, "api_key", "") or "").strip()
            global_api_key = str(visible_config.provider.litellm_api_key or "").strip()
            if cfg_api_key:
                provider_configured = True
                provider_source = f"config_file:{visible_config_path}:providers.{provider_name}.api_key"
            elif global_api_key:
                provider_configured = True
                provider_source = f"config_file:{visible_config_path}:provider.litellm_api_key"
    elif provider_auth_mode == "oauth":
        provider_envs.extend(DOCKER_OAUTH_ENV_GROUPS.get(provider_name, ()))
        if visible_config is not None and provider_name:
            auth_cfg = getattr(visible_config.auth.providers, provider_name, None)
            visible_token = str(getattr(auth_cfg, "access_token", "") or "").strip()
            if visible_token:
                provider_configured = True
                provider_source = f"config_file:{visible_config_path}:auth.providers.{provider_name}.access_token"
        if not provider_configured:
            oauth_status = resolve_oauth_provider_auth(config, provider_name) if provider_name else {"configured": False, "source": ""}
            if str(oauth_status.get("source", "") or "").startswith("env:"):
                provider_configured = bool(oauth_status.get("configured", False))
                provider_source = str(oauth_status.get("source", "") or "")

    available_envs: list[dict[str, str]] = []
    missing_envs: list[str] = []
    seen_envs: set[str] = set()
    for env_name in provider_envs:
        if not env_name or env_name in seen_envs:
            continue
        seen_envs.add(env_name)
        value, source = _docker_effective_env_value(env_name, env_file_values)
        if value:
            available_envs.append({"name": env_name, "source": source})
        else:
            missing_envs.append(env_name)
    if available_envs and not provider_configured:
        provider_configured = True
        provider_source = f"{available_envs[0]['source']}:{available_envs[0]['name']}"

    payload["provider"] = {
        "detected": provider_name,
        "model": provider_model,
        "auth_mode": provider_auth_mode,
        "configured": provider_configured,
        "configured_source": provider_source,
        "available_envs": available_envs,
        "missing_envs": missing_envs,
    }

    if provider_name and provider_auth_mode in {"api_key", "oauth"} and not provider_configured and not available_envs:
        missing_display = ", ".join(missing_envs) if missing_envs else "the provider-specific auth envs"
        if provider_auth_mode == "oauth":
            payload["warnings"].append(f"docker_provider_oauth_missing:{provider_name}")
            payload["hints"].append(
                "Provider "
                f"'{provider_name}' for model '{provider_model or provider_name}' has no Docker-side OAuth auth available. "
                f"Set one of {missing_display} {_docker_secret_hint_target(env_file)}."
            )
        else:
            payload["warnings"].append(f"docker_provider_env_missing:{provider_name}")
            payload["hints"].append(
                "Provider "
                f"'{provider_name}' for model '{provider_model or provider_name}' has no Docker-side API key available. "
                f"Set one of {missing_display} {_docker_secret_hint_target(env_file)}."
            )

    auth_mode, auth_mode_source = _docker_effective_env_value("CLAWLITE_GATEWAY_AUTH_MODE", env_file_values)
    gateway_mode = auth_mode if auth_mode in {"off", "optional", "required"} else (
        str(visible_config.gateway.auth.mode or "off").strip().lower() if visible_config is not None else "off"
    )
    gateway_token, gateway_token_source = _docker_effective_env_value("CLAWLITE_GATEWAY_AUTH_TOKEN", env_file_values)
    if not gateway_token and visible_config is not None:
        configured_token = str(visible_config.gateway.auth.token or "").strip()
        if configured_token:
            gateway_token = configured_token
            gateway_token_source = f"config_file:{visible_config_path}:gateway.auth.token"
    payload["gateway_auth"] = {
        "mode": gateway_mode,
        "token_configured": bool(gateway_token),
        "token_source": gateway_token_source or auth_mode_source,
        "error": "",
    }
    if gateway_mode == "required" and not gateway_token:
        payload["ok"] = False
        payload["error"] = "docker_gateway_auth_token_missing"
        payload["errors"].append("docker_gateway_auth_token_missing")
        payload["gateway_auth"]["error"] = "docker_gateway_auth_token_missing"
        payload["hints"].append(
            "Gateway auth is required for this Docker runtime but no token is available. "
            f"Set CLAWLITE_GATEWAY_AUTH_TOKEN {_docker_secret_hint_target(env_file)}."
        )

    return payload


def docker_preflight_probe(
    *,
    timeout: float = 3.0,
    config: Any | None = None,
    config_path: str | Path | None = None,
    config_profile: str | None = None,
    provider_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package_root = Path(__file__).resolve().parents[2]
    roots: list[Path] = []
    for candidate in (Path.cwd(), package_root):
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)

    repo_root = package_root
    repo_root_source = "package"
    for candidate in roots:
        if (candidate / "docker-compose.yml").exists():
            repo_root = candidate
            repo_root_source = "cwd" if candidate == roots[0] else "package"
            break

    compose_file = repo_root / "docker-compose.yml"
    probe_timeout = max(1.0, float(timeout))
    payload: dict[str, Any] = {
        "enabled": True,
        "ok": False,
        "repo_root": str(repo_root),
        "repo_root_source": repo_root_source,
        "compose_file": str(compose_file),
        "env_file": {"configured": False, "ok": True, "path": "", "error": ""},
        "docker_available": False,
        "compose_version": {"ok": False, "exit_code": 0, "detail": ""},
        "compose_config": {"ok": False, "exit_code": 0, "detail": ""},
        "secrets": {
            "ok": True,
            "error": "",
            "errors": [],
            "warnings": [],
            "hints": [],
            "provider": {
                "detected": "",
                "model": "",
                "auth_mode": "",
                "configured": False,
                "configured_source": "",
                "available_envs": [],
                "missing_envs": [],
            },
            "gateway_auth": {
                "mode": "",
                "token_configured": False,
                "token_source": "",
                "error": "",
            },
        },
        "stack": {
            "detected": False,
            "ok": True,
            "error": "",
            "service_count": 0,
            "runtime_service_count": 0,
            "running_count": 0,
            "unhealthy_services": [],
            "ignored_services": [],
            "services": [],
        },
        "gateway": {
            "detected": False,
            "running": False,
            "ok": True,
            "state": "",
            "health": "",
            "status": "not_running",
            "error": "",
        },
    }
    if not compose_file.exists():
        payload["error"] = "docker_compose_missing"
        return payload

    env_file = _docker_env_file_details(repo_root)
    payload["env_file"] = env_file
    if env_file.get("configured") and not env_file.get("ok"):
        payload["error"] = "docker_env_file_missing"
        return payload
    payload["secrets"] = _docker_secret_status(
        config=config,
        config_path=config_path,
        config_profile=config_profile,
        provider_check=provider_check,
        env_file=env_file,
    )
    if not payload["secrets"]["ok"]:
        payload["error"] = str(payload["secrets"]["error"] or "")
        return payload
    compose_args: list[str] = []
    if env_file.get("configured"):
        compose_args = ["--env-file", str(env_file.get("path") or "")]

    docker_bin = shutil.which("docker")
    if not docker_bin:
        payload["error"] = "docker_missing"
        return payload
    payload["docker_available"] = True

    try:
        version = subprocess.run(
            [docker_bin, "compose", *compose_args, "version"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=probe_timeout,
        )
    except Exception as exc:
        payload["error"] = "docker_compose_unavailable"
        payload["error_detail"] = _trim_probe_output(exc)
        return payload

    payload["compose_version"] = {
        "ok": version.returncode == 0,
        "exit_code": int(version.returncode),
        "detail": _trim_probe_output(version.stdout or version.stderr),
    }
    if version.returncode != 0:
        payload["error"] = "docker_compose_unavailable"
        payload["error_detail"] = _trim_probe_output(version.stderr or version.stdout)
        return payload

    try:
        compose = subprocess.run(
            [docker_bin, "compose", *compose_args, "config"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=probe_timeout,
        )
    except Exception as exc:
        payload["error"] = "docker_compose_config_failed"
        payload["error_detail"] = _trim_probe_output(exc)
        return payload

    payload["compose_config"] = {
        "ok": compose.returncode == 0,
        "exit_code": int(compose.returncode),
        "detail": _trim_probe_output(compose.stderr or compose.stdout),
    }
    if compose.returncode != 0:
        payload["error"] = "docker_compose_config_failed"
        payload["error_detail"] = _trim_probe_output(compose.stderr or compose.stdout)
        return payload

    try:
        ps = subprocess.run(
            [docker_bin, "compose", *compose_args, "ps", "--format", "json"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=probe_timeout,
        )
    except Exception as exc:
        payload["error"] = "docker_compose_ps_failed"
        payload["error_detail"] = _trim_probe_output(exc)
        return payload

    if ps.returncode != 0:
        payload["gateway"]["ok"] = False
        payload["gateway"]["error"] = _trim_probe_output(ps.stderr or ps.stdout)
        payload["error"] = "docker_compose_ps_failed"
        payload["error_detail"] = _trim_probe_output(ps.stderr or ps.stdout)
        return payload

    rows = _docker_compose_rows(ps.stdout)
    if not rows:
        payload["ok"] = True
        return payload

    services = [_docker_service_summary(row) for row in rows]
    ignored_services = sorted(service["service"] for service in services if service["service"] == "clawlite-cli")
    runtime_services = [service for service in services if service["service"] != "clawlite-cli"]
    unhealthy_services = sorted(service["service"] for service in runtime_services if not service["ok"])
    payload["stack"] = {
        "detected": bool(runtime_services),
        "ok": not unhealthy_services,
        "error": "",
        "service_count": len(services),
        "runtime_service_count": len(runtime_services),
        "running_count": sum(1 for service in runtime_services if service["running"]),
        "unhealthy_services": unhealthy_services,
        "ignored_services": ignored_services,
        "services": services,
    }
    if not runtime_services:
        payload["ok"] = True
        return payload

    gateway = next((service for service in runtime_services if service["service"] == "clawlite-gateway"), None)
    if gateway is None:
        payload["stack"]["error"] = "docker_gateway_not_running"
        payload["gateway"]["error"] = "docker_gateway_not_running"
        payload["error"] = "docker_gateway_not_running"
        payload["ok"] = False
        return payload

    gateway_ok = bool(gateway["ok"]) and str(gateway.get("health") or "") in {"", "healthy"}
    payload["gateway"] = {
        "detected": True,
        "running": bool(gateway["running"]),
        "ok": gateway_ok,
        "state": str(gateway["state"] or ""),
        "health": str(gateway["health"] or ""),
        "status": str(gateway["status"] or ""),
        "error": "",
    }
    if not gateway_ok:
        payload["stack"]["error"] = "docker_gateway_not_healthy"
        payload["gateway"]["error"] = "docker_gateway_not_healthy"
        payload["error"] = "docker_gateway_not_healthy"
        payload["ok"] = False
        return payload

    non_gateway_unhealthy = [service for service in unhealthy_services if service != "clawlite-gateway"]
    if non_gateway_unhealthy:
        payload["stack"]["error"] = "docker_stack_not_healthy"
        payload["error"] = "docker_stack_not_healthy"
        payload["ok"] = False
        return payload

    payload["ok"] = True
    return payload


def cmd_validate_preflight(args: argparse.Namespace) -> int:
    config_path = str(args.config) if args.config else str(DEFAULT_CONFIG_PATH)
    config_profile = getattr(args, "profile", None)
    strict_block: dict[str, Any]
    try:
        strict_cfg = load_config(args.config, strict=True, profile=config_profile)
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

    cfg = load_config(args.config, profile=config_profile)
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

    docker_check: dict[str, Any] = {"enabled": bool(args.docker), "ok": True}
    if bool(args.docker):
        docker_check = docker_preflight_probe(
            timeout=float(args.timeout),
            config=cfg,
            config_path=args.config,
            config_profile=config_profile,
            provider_check=dict(local_checks["provider"]),
        )

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
    if docker_check.get("enabled", False):
        enabled_blocks.append(docker_check)

    ok = all(bool(block.get("ok", False)) for block in enabled_blocks)
    payload = {
        "ok": ok,
        "strict_config": strict_block,
        "local_checks": local_checks,
        "gateway_probe": gateway_check,
        "provider_live_probe": provider_live_check,
        "telegram_live_probe": telegram_live_check,
        "docker_preflight": docker_check,
    }
    _print_json(payload)
    return 0 if ok else 2


def cmd_tools_safety(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    raw_arguments = str(args.args_json or "{}").strip() or "{}"
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        _print_json({"ok": False, "error": f"invalid_arguments_json:{exc.msg}"})
        return 1
    if not isinstance(arguments, dict):
        _print_json({"ok": False, "error": "invalid_arguments_json:expected_object"})
        return 1

    registry = ToolRegistry(safety=config.tools.safety)
    payload = registry.safety_decision(
        args.tool,
        arguments,
        session_id=str(args.session_id or ""),
        channel=str(args.channel or ""),
    )
    payload["ok"] = True
    payload["action"] = "tools_safety_preview"
    _print_json(payload)
    return 0


def cmd_tools_catalog(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    gateway_url = str(args.gateway_url or "").strip()
    if not gateway_url:
        gateway_url = f"http://{config.gateway.host}:{int(config.gateway.port)}"
    payload = fetch_gateway_tools_catalog(
        gateway_url=gateway_url,
        include_schema=bool(args.include_schema),
        timeout=float(args.timeout),
        token=str(args.token or ""),
    )
    if payload.get("ok", False) and args.group:
        wanted = str(args.group or "").strip().lower()
        payload["groups"] = [
            row for row in list(payload.get("groups", []) or [])
            if str(row.get("id", "") or "").strip().lower() == wanted
        ]
        payload["tool_count"] = sum(len(list(row.get("tools", []) or [])) for row in payload["groups"])
        payload["group_filter"] = wanted
    payload["action"] = "tools_catalog"
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_tools_show(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    gateway_url = str(args.gateway_url or "").strip()
    if not gateway_url:
        gateway_url = f"http://{config.gateway.host}:{int(config.gateway.port)}"
    catalog = fetch_gateway_tools_catalog(
        gateway_url=gateway_url,
        include_schema=True,
        timeout=float(args.timeout),
        token=str(args.token or ""),
    )
    if not catalog.get("ok", False):
        catalog["action"] = "tools_show"
        _print_json(catalog)
        return 2

    needle = str(args.name or "").strip()
    aliases = dict(catalog.get("aliases", {}) or {})
    resolved_name = aliases.get(needle, needle)
    schema_rows = list(catalog.get("schema", []) or [])
    selected_schema = next((row for row in schema_rows if str(row.get("name", "") or "") == resolved_name), None)
    group_id = ""
    group_label = ""
    description = ""
    for group in list(catalog.get("groups", []) or []):
        for tool in list(group.get("tools", []) or []):
            if str(tool.get("id", "") or "") != resolved_name:
                continue
            group_id = str(group.get("id", "") or "")
            group_label = str(group.get("label", "") or "")
            description = str(tool.get("description", "") or "")
            break
        if group_id:
            break

    if selected_schema is None and not group_id:
        _print_json(
            {
                "ok": False,
                "action": "tools_show",
                "error": f"tool_not_found:{needle}",
                "requested_name": needle,
                "base_url": catalog.get("base_url", ""),
                "endpoint": catalog.get("endpoint", ""),
            }
        )
        return 1

    payload = {
        "ok": True,
        "action": "tools_show",
        "requested_name": needle,
        "resolved_name": resolved_name,
        "alias_of": resolved_name if resolved_name != needle else "",
        "group": {"id": group_id, "label": group_label} if group_id else {},
        "description": description or str((selected_schema or {}).get("description", "") or ""),
        "schema": selected_schema or {},
        "base_url": catalog.get("base_url", ""),
        "endpoint": catalog.get("endpoint", ""),
    }
    _print_json(payload)
    return 0


def cmd_tools_approvals(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    payload = fetch_gateway_tool_approvals(
        config,
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
        status=str(args.status or "pending"),
        session_id=str(args.session_id or ""),
        channel=str(args.channel or ""),
        tool=str(args.tool or ""),
        rule=str(args.rule or ""),
        include_grants=bool(args.include_grants),
        limit=max(1, int(args.limit or 1)),
    )
    payload["action"] = "tools_approvals"
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_tools_approve(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    payload = review_gateway_tool_approval(
        config,
        request_id=str(args.request_id or ""),
        decision="approved",
        actor=str(args.actor or ""),
        note=str(args.note or ""),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    payload["action"] = "tools_approve"
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_tools_reject(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    payload = review_gateway_tool_approval(
        config,
        request_id=str(args.request_id or ""),
        decision="rejected",
        actor=str(args.actor or ""),
        note=str(args.note or ""),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    payload["action"] = "tools_reject"
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_tools_revoke_grant(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    payload = revoke_gateway_tool_grants(
        config,
        session_id=str(args.session_id or ""),
        channel=str(args.channel or ""),
        rule=str(args.rule or ""),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    payload["action"] = "tools_revoke_grant"
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


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
    cfg = load_config(args.config)
    runtime = _build_runtime_for_args(args, cfg)

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
    cfg = load_config(args.config)
    runtime = _build_runtime_for_args(args, cfg)
    rows = runtime.cron.list_jobs(session_id=args.session_id)
    _print_json({"jobs": rows})
    return 0


def cmd_cron_remove(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    runtime = _build_runtime_for_args(args, cfg)
    ok = runtime.cron.remove_job(args.job_id)
    _print_json({"ok": ok})
    return 0


def cmd_cron_enable(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    runtime = _build_runtime_for_args(args, cfg)
    ok = runtime.cron.enable_job(args.job_id, enabled=True)
    _print_json({"ok": ok, "job_id": args.job_id, "enabled": True})
    return 0


def cmd_cron_disable(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    runtime = _build_runtime_for_args(args, cfg)
    ok = runtime.cron.enable_job(args.job_id, enabled=False)
    _print_json({"ok": ok, "job_id": args.job_id, "enabled": False})
    return 0


def cmd_cron_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    runtime = _build_runtime_for_args(args, cfg)

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
                "skill_key": row.skill_key or row.name,
                "primary_env": row.primary_env,
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
            "skill_key": row.skill_key or row.name,
            "primary_env": row.primary_env,
            "description": row.description,
            "always": row.always,
            "source": row.source,
            "available": row.available,
            "enabled": row.enabled,
            "pinned": row.pinned,
            "status": skills_doctor_status(
                {
                    "name": row.name,
                    "skill_key": row.skill_key or row.name,
                    "primary_env": row.primary_env,
                    "available": row.available,
                    "enabled": row.enabled,
                    "missing": row.missing,
                    "contract_issues": row.contract_issues,
                    "fallback_hint": row.fallback_hint,
                }
            ),
            "hint": skills_doctor_hint(
                {
                    "name": row.name,
                    "skill_key": row.skill_key or row.name,
                    "primary_env": row.primary_env,
                    "available": row.available,
                    "enabled": row.enabled,
                    "missing": row.missing,
                    "contract_issues": row.contract_issues,
                    "fallback_hint": row.fallback_hint,
                }
            ),
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


def cmd_skills_refresh(args: argparse.Namespace) -> int:
    cfg = load_config(args.config, profile=getattr(args, "profile", None))
    payload = skills_refresh(
        cfg,
        force=bool(args.force),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_skills_doctor(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    diagnostics = loader.diagnostics_report()
    payload = skills_doctor_report(
        diagnostics,
        include_all=bool(args.all),
        status=str(getattr(args, "status", "") or ""),
        source=str(getattr(args, "source", "") or ""),
        query=str(getattr(args, "query", "") or ""),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def cmd_skills_validate(args: argparse.Namespace) -> int:
    cfg = load_config(args.config, profile=getattr(args, "profile", None))
    payload = skills_validate(
        cfg,
        force=bool(args.force),
        include_all=bool(args.all),
        status=str(getattr(args, "status", "") or ""),
        source=str(getattr(args, "source", "") or ""),
        query=str(getattr(args, "query", "") or ""),
        gateway_url=str(args.gateway_url or ""),
        token=str(args.token or ""),
        timeout=float(args.timeout),
    )
    _print_json(payload)
    return 0 if payload.get("ok", False) else 2


def _skills_lifecycle_payload(action: str, row: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "name": row.name,
        "skill_key": row.skill_key or row.name,
        "enabled": row.enabled,
        "pinned": row.pinned,
        "version_pin": row.version_pin,
        "available": row.available,
        "version": row.version,
        "source": row.source,
        "path": str(row.path),
    }


def _managed_skill_slug(row: Any) -> str:
    try:
        return str(Path(row.path).parent.name).strip()
    except Exception:
        return ""


def _managed_skill_status(row: Any) -> str:
    return skills_doctor_status(
        {
            "name": getattr(row, "name", ""),
            "skill_key": getattr(row, "skill_key", "") or getattr(row, "name", ""),
            "available": bool(getattr(row, "available", False)),
            "enabled": bool(getattr(row, "enabled", True)),
            "missing": list(getattr(row, "missing", []) or []),
            "contract_issues": list(getattr(row, "contract_issues", []) or []),
        }
    )


def _managed_skill_hint(row: Any) -> str:
    return skills_doctor_hint(
        {
            "name": getattr(row, "name", ""),
            "skill_key": getattr(row, "skill_key", "") or getattr(row, "name", ""),
            "primary_env": getattr(row, "primary_env", ""),
            "available": bool(getattr(row, "available", False)),
            "enabled": bool(getattr(row, "enabled", True)),
            "missing": list(getattr(row, "missing", []) or []),
            "contract_issues": list(getattr(row, "contract_issues", []) or []),
            "fallback_hint": getattr(row, "fallback_hint", ""),
        }
    )


def _managed_skill_payload(row: Any) -> dict[str, Any]:
    return {
        "slug": _managed_skill_slug(row),
        "name": row.name,
        "skill_key": row.skill_key or row.name,
        "primary_env": row.primary_env,
        "description": row.description,
        "available": row.available,
        "enabled": row.enabled,
        "pinned": row.pinned,
        "status": _managed_skill_status(row),
        "hint": _managed_skill_hint(row),
        "version": row.version,
        "version_pin": row.version_pin,
        "missing": row.missing,
        "homepage": row.homepage,
        "fallback_hint": row.fallback_hint,
        "path": str(row.path),
    }


def _managed_skill_rows(loader: SkillsLoader, *, status: str = "") -> list[Any]:
    rows = [row for row in loader.discover(include_unavailable=True) if row.source == "marketplace"]
    wanted_status = str(status or "").strip().lower()
    if wanted_status:
        rows = [row for row in rows if _managed_skill_status(row) == wanted_status]
    return rows


def _managed_skill_status_counts(rows: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = _managed_skill_status(row)
        counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _resolve_managed_skill(loader: SkillsLoader, raw_name: str) -> tuple[Any | None, str, Path]:
    needle = str(raw_name or "").strip().lower()
    managed_root = _skills_managed_root(loader)
    fallback = managed_root / "skills" / str(raw_name or "").strip()
    if not needle:
        return None, "", fallback

    rows = [row for row in loader.discover(include_unavailable=True) if row.source == "marketplace"]
    for row in rows:
        slug = _managed_skill_slug(row)
        candidates = {
            slug.lower(),
            str(getattr(row, "name", "") or "").strip().lower(),
            str(getattr(row, "skill_key", "") or "").strip().lower(),
        }
        if needle not in candidates:
            continue
        resolved_slug = slug or str(raw_name or "").strip()
        return row, resolved_slug, managed_root / "skills" / resolved_slug
    return None, "", fallback


def cmd_skills_config(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row = loader.get(args.name)
    if row is None:
        _print_json({"ok": False, "error": f"skill_not_found:{args.name}"})
        return 1

    if bool(getattr(args, "enable", False)) and bool(getattr(args, "disable", False)):
        _print_json({"ok": False, "error": "skills_config_conflicting_enabled_flags"})
        return 1
    if bool(getattr(args, "clear", False)) and (
        str(getattr(args, "api_key", "") or "").strip()
        or bool(getattr(args, "clear_api_key", False))
        or list(getattr(args, "env", []) or [])
        or bool(getattr(args, "clear_env", False))
        or bool(getattr(args, "enable", False))
        or bool(getattr(args, "disable", False))
    ):
        _print_json({"ok": False, "error": "skills_config_clear_conflicts_with_other_flags"})
        return 1
    if bool(getattr(args, "clear_api_key", False)) and str(getattr(args, "api_key", "") or "").strip():
        _print_json({"ok": False, "error": "skills_config_conflicting_api_key_flags"})
        return 1

    skill_key = row.skill_key or row.name
    target_path = config_payload_path(getattr(args, "config", None), profile=getattr(args, "profile", None))
    payload = load_target_config_payload(getattr(args, "config", None), profile=getattr(args, "profile", None))
    skills_cfg = dict(payload.get("skills") or {})
    entries = dict(skills_cfg.get("entries") or {})
    current_entry = dict(entries.get(skill_key) or {})

    mutation_requested = any(
        [
            bool(getattr(args, "clear", False)),
            bool(getattr(args, "clear_api_key", False)),
            bool(getattr(args, "clear_env", False)),
            bool(getattr(args, "enable", False)),
            bool(getattr(args, "disable", False)),
            bool(list(getattr(args, "env", []) or [])),
            bool(str(getattr(args, "api_key", "") or "").strip()),
        ]
    )
    if not mutation_requested:
        _print_json(
            {
                "ok": True,
                "action": "skills_config_show",
                "name": row.name,
                "skill_key": skill_key,
                "primary_env": row.primary_env,
                "config_path": str(target_path),
                "entry": current_entry,
            }
        )
        return 0

    if bool(getattr(args, "clear", False)):
        entries.pop(skill_key, None)
    else:
        entry = dict(current_entry)
        if bool(getattr(args, "clear_api_key", False)):
            entry.pop("apiKey", None)
            entry.pop("api_key", None)
        api_key = str(getattr(args, "api_key", "") or "").strip()
        if api_key:
            entry["apiKey"] = api_key

        if bool(getattr(args, "clear_env", False)):
            entry.pop("env", None)
        env_values = list(getattr(args, "env", []) or [])
        if env_values:
            merged_env = dict(entry.get("env") or {})
            merged_env.update(_parse_skill_env_assignments(env_values))
            entry["env"] = merged_env

        if bool(getattr(args, "enable", False)):
            entry["enabled"] = True
        elif bool(getattr(args, "disable", False)):
            entry["enabled"] = False

        if entry:
            entries[skill_key] = entry
        else:
            entries.pop(skill_key, None)

    if entries:
        skills_cfg["entries"] = entries
    else:
        skills_cfg.pop("entries", None)
    if skills_cfg:
        payload["skills"] = skills_cfg
    else:
        payload.pop("skills", None)

    saved_path = save_raw_config_payload(payload, getattr(args, "config", None), profile=getattr(args, "profile", None))
    updated_payload = load_target_config_payload(getattr(args, "config", None), profile=getattr(args, "profile", None))
    updated_entry = dict(dict(updated_payload.get("skills") or {}).get("entries") or {}).get(skill_key, {})
    _print_json(
        {
            "ok": True,
            "action": "skills_config",
            "name": row.name,
            "skill_key": skill_key,
            "primary_env": row.primary_env,
            "config_path": str(saved_path),
            "entry": updated_entry,
        }
    )
    return 0


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


def cmd_skills_install(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    rc, payload = _run_clawhub_command(loader, "install", args.slug)
    payload["action"] = "install"
    payload["slug"] = args.slug
    if rc == 0:
        refreshed_loader = _skills_loader_for_args(args)
        resolved_row, _slug, _target = _resolve_managed_skill(refreshed_loader, args.slug)
        if resolved_row is not None:
            payload["resolved"] = _managed_skill_payload(resolved_row)
        rows = _managed_skill_rows(refreshed_loader)
        payload["managed_count"] = len(rows)
        payload["status_counts"] = _managed_skill_status_counts(rows)
    _print_json(payload)
    return rc


def cmd_skills_update(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    row, slug, _target = _resolve_managed_skill(loader, args.name)
    resolved_slug = slug or str(args.name).strip()
    rc, payload = _run_clawhub_command(loader, "update", resolved_slug)
    payload["action"] = "update"
    payload["slug"] = resolved_slug
    if row is not None:
        payload["name"] = row.name
        payload["skill_key"] = row.skill_key or row.name
    if rc == 0:
        refreshed_loader = _skills_loader_for_args(args)
        resolved_row, _final_slug, _target = _resolve_managed_skill(refreshed_loader, resolved_slug)
        if resolved_row is not None:
            payload["resolved"] = _managed_skill_payload(resolved_row)
        rows = _managed_skill_rows(refreshed_loader)
        payload["managed_count"] = len(rows)
        payload["status_counts"] = _managed_skill_status_counts(rows)
    _print_json(payload)
    return rc


def cmd_skills_sync(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    payload = skills_sync_report(loader)
    _print_json(payload)
    return int(payload.get("returncode", 0 if payload.get("ok", False) else 1) or 0)


def cmd_skills_search(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    rc, payload = _run_clawhub_command(loader, "search", args.query, "--limit", str(max(1, int(args.limit or 5))))
    payload["action"] = "search"
    payload["query"] = args.query
    payload["limit"] = max(1, int(args.limit or 5))
    all_rows = _managed_skill_rows(loader)
    query = str(args.query or "").strip().lower()
    local_matches = [
        _managed_skill_payload(row)
        for row in all_rows
        if not query
        or query in _managed_skill_slug(row).lower()
        or query in str(getattr(row, "name", "") or "").strip().lower()
        or query in str(getattr(row, "skill_key", "") or "").strip().lower()
        or query in str(getattr(row, "description", "") or "").strip().lower()
    ]
    payload["managed_count"] = len(all_rows)
    payload["status_counts"] = _managed_skill_status_counts(all_rows)
    payload["local_matches"] = local_matches
    _print_json(payload)
    return rc


def cmd_skills_managed(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    _print_json(
        skills_managed_report(
            loader,
            status=str(getattr(args, "status", "") or ""),
            query=str(getattr(args, "query", "") or ""),
        )
    )
    return 0


def cmd_skills_remove(args: argparse.Namespace) -> int:
    loader = _skills_loader_for_args(args)
    managed_root = _skills_managed_root(loader)
    row, slug, target = _resolve_managed_skill(loader, args.name)
    if row is None or not target.exists():
        _print_json(
            {
                "ok": False,
                "error": f"managed_skill_not_found:{args.name}",
                "managed_root": str(managed_root),
            }
        )
        return 1
    removed_payload = _managed_skill_payload(row)
    shutil.rmtree(target)
    refreshed_loader = _skills_loader_for_args(args)
    remaining_rows = _managed_skill_rows(refreshed_loader)
    _print_json(
        {
            "ok": True,
            "action": "remove",
            "name": row.name,
            "skill_key": row.skill_key or row.name,
            "slug": slug,
            "removed": removed_payload,
            "removed_path": str(target),
            "managed_root": str(managed_root),
            "managed_count": len(remaining_rows),
            "status_counts": _managed_skill_status_counts(remaining_rows),
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawlite",
        description="ClawLite autonomous assistant CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--config", default=None, help="Path to config JSON/YAML")
    parser.add_argument("--profile", default=None, help="Optional config profile overlay name")
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
    p_validate_preflight.add_argument("--docker", action="store_true", help="Run Docker/Compose deployment probes when Docker is available")
    p_validate_preflight.set_defaults(handler=cmd_validate_preflight)

    p_tools = sub.add_parser("tools", help="Inspect tool policy and behavior")
    tools_sub = p_tools.add_subparsers(dest="tools_command", required=True)

    p_tools_safety = tools_sub.add_parser("safety", help="Preview effective tool safety for one call")
    p_tools_safety.add_argument("tool")
    p_tools_safety.add_argument("--session-id", default="")
    p_tools_safety.add_argument("--channel", default="")
    p_tools_safety.add_argument("--args-json", default="{}")
    p_tools_safety.set_defaults(handler=cmd_tools_safety)

    p_tools_catalog = tools_sub.add_parser("catalog", help="Fetch the live gateway tools catalog")
    p_tools_catalog.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_tools_catalog.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_tools_catalog.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_tools_catalog.add_argument("--include-schema", action="store_true", help="Include JSON schema rows in the catalog response")
    p_tools_catalog.add_argument("--group", default="", help="Optional group filter, e.g. runtime or web")
    p_tools_catalog.set_defaults(handler=cmd_tools_catalog)

    p_tools_show = tools_sub.add_parser("show", help="Show one live tool entry from the gateway catalog")
    p_tools_show.add_argument("name")
    p_tools_show.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_tools_show.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_tools_show.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_tools_show.set_defaults(handler=cmd_tools_show)

    p_tools_approvals = tools_sub.add_parser("approvals", help="List live pending/reviewed tool approvals from the gateway")
    p_tools_approvals.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_tools_approvals.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_tools_approvals.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_tools_approvals.add_argument("--status", choices=["pending", "approved", "rejected", "all"], default="pending")
    p_tools_approvals.add_argument("--session-id", default="", help="Optional session filter")
    p_tools_approvals.add_argument("--channel", default="", help="Optional channel filter")
    p_tools_approvals.add_argument("--tool", default="", help="Optional tool filter")
    p_tools_approvals.add_argument("--rule", default="", help="Optional approval rule filter")
    p_tools_approvals.add_argument("--include-grants", action="store_true", help="Include active approval grants in the response")
    p_tools_approvals.add_argument("--limit", type=int, default=50)
    p_tools_approvals.set_defaults(handler=cmd_tools_approvals)

    p_tools_approve = tools_sub.add_parser("approve", help="Approve one pending tool request through the gateway")
    p_tools_approve.add_argument("request_id")
    p_tools_approve.add_argument(
        "--actor",
        default="",
        help="Compatibility-only label; generic gateway reviews are recorded as control-plane",
    )
    p_tools_approve.add_argument("--note", default="", help="Optional review note")
    p_tools_approve.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_tools_approve.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_tools_approve.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_tools_approve.set_defaults(handler=cmd_tools_approve)

    p_tools_reject = tools_sub.add_parser("reject", help="Reject one pending tool request through the gateway")
    p_tools_reject.add_argument("request_id")
    p_tools_reject.add_argument(
        "--actor",
        default="",
        help="Compatibility-only label; generic gateway reviews are recorded as control-plane",
    )
    p_tools_reject.add_argument("--note", default="", help="Optional review note")
    p_tools_reject.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_tools_reject.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_tools_reject.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_tools_reject.set_defaults(handler=cmd_tools_reject)

    p_tools_revoke_grant = tools_sub.add_parser("revoke-grant", help="Revoke active temporary approval grants through the gateway")
    p_tools_revoke_grant.add_argument("--session-id", default="", help="Optional session filter")
    p_tools_revoke_grant.add_argument("--channel", default="", help="Optional channel filter")
    p_tools_revoke_grant.add_argument("--rule", default="", help="Optional approval specifier filter")
    p_tools_revoke_grant.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_tools_revoke_grant.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_tools_revoke_grant.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_tools_revoke_grant.set_defaults(handler=cmd_tools_revoke_grant)

    p_provider = sub.add_parser("provider", help="Provider auth lifecycle commands")
    provider_sub = p_provider.add_subparsers(dest="provider_command", required=True)

    p_provider_login = provider_sub.add_parser("login", help="Login and persist provider auth")
    p_provider_login.add_argument("provider", choices=["openai-codex", "gemini-oauth", "qwen-oauth"])
    p_provider_login.add_argument("--access-token", default="", help="Explicit OAuth access token")
    p_provider_login.add_argument("--account-id", default="", help="Optional provider account/org id")
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
    p_provider_logout.add_argument("provider", nargs="?", default="openai-codex", choices=["openai-codex", "gemini-oauth", "qwen-oauth"])
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

    p_self_evolution = sub.add_parser("self-evolution", help="Self-evolution control commands")
    self_evolution_sub = p_self_evolution.add_subparsers(dest="self_evolution_command", required=True)

    p_self_evolution_status = self_evolution_sub.add_parser("status", help="Fetch self-evolution status from the gateway")
    p_self_evolution_status.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_self_evolution_status.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_self_evolution_status.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_self_evolution_status.set_defaults(handler=cmd_self_evolution_status)

    p_self_evolution_trigger = self_evolution_sub.add_parser("trigger", help="Trigger one self-evolution run via the gateway")
    p_self_evolution_trigger.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_self_evolution_trigger.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_self_evolution_trigger.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_self_evolution_trigger.add_argument("--dry-run", action="store_true", help="Preview proposal without applying or committing")
    p_self_evolution_trigger.set_defaults(handler=cmd_self_evolution_trigger)

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

    p_skills_config = skills_sub.add_parser(
        "config",
        help="Show or update skills.entries.<skillKey> config for one skill",
    )
    p_skills_config.add_argument("name")
    p_skills_config.add_argument("--api-key", default="", help="Set skills.entries.<skillKey>.apiKey")
    p_skills_config.add_argument("--clear-api-key", action="store_true", help="Remove skills.entries.<skillKey>.apiKey")
    p_skills_config.add_argument(
        "--env",
        action="append",
        default=[],
        help="Add or update one env override as KEY=VALUE; repeat for multiple values",
    )
    p_skills_config.add_argument("--clear-env", action="store_true", help="Remove all env overrides for the skill")
    p_skills_config.add_argument("--enable", action="store_true", help="Set skills.entries.<skillKey>.enabled=true")
    p_skills_config.add_argument("--disable", action="store_true", help="Set skills.entries.<skillKey>.enabled=false")
    p_skills_config.add_argument("--clear", action="store_true", help="Remove the entire skills.entries.<skillKey> entry")
    p_skills_config.set_defaults(handler=cmd_skills_config)

    p_skills_check = skills_sub.add_parser("check", help="Emit aggregated deterministic skills diagnostics")
    p_skills_check.set_defaults(handler=cmd_skills_check)

    p_skills_refresh = skills_sub.add_parser("refresh", help="Trigger runtime skill discovery refresh through the gateway")
    p_skills_refresh.add_argument("--no-force", dest="force", action="store_false", help="Let the runtime refresh path respect debounce instead of forcing discovery")
    p_skills_refresh.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_skills_refresh.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_skills_refresh.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_skills_refresh.set_defaults(handler=cmd_skills_refresh, force=True)

    p_skills_doctor = skills_sub.add_parser("doctor", help="Emit actionable remediation hints for skill availability issues")
    p_skills_doctor.add_argument("--all", action="store_true", help="Include ready and disabled skills in the report")
    p_skills_doctor.add_argument(
        "--status",
        choices=["ready", "missing_requirements", "policy_blocked", "disabled", "invalid_contract", "unavailable"],
        default="",
        help="Optional status filter for the doctor output",
    )
    p_skills_doctor.add_argument(
        "--source",
        choices=["builtin", "workspace", "marketplace"],
        default="",
        help="Optional source filter for the doctor output",
    )
    p_skills_doctor.add_argument("--query", default="", help="Optional case-insensitive search filter")
    p_skills_doctor.set_defaults(handler=cmd_skills_doctor)

    p_skills_validate = skills_sub.add_parser(
        "validate",
        help="Refresh runtime discovery and emit actionable blocked-skills diagnostics",
    )
    p_skills_validate.add_argument(
        "--no-force",
        dest="force",
        action="store_false",
        help="Let the runtime refresh path respect debounce instead of forcing discovery",
    )
    p_skills_validate.add_argument("--all", action="store_true", help="Include ready and disabled skills in the report")
    p_skills_validate.add_argument(
        "--status",
        choices=["ready", "missing_requirements", "policy_blocked", "disabled", "invalid_contract", "unavailable"],
        default="",
        help="Optional status filter for the validation output",
    )
    p_skills_validate.add_argument(
        "--source",
        choices=["builtin", "workspace", "marketplace"],
        default="",
        help="Optional source filter for the validation output",
    )
    p_skills_validate.add_argument("--query", default="", help="Optional case-insensitive search filter")
    p_skills_validate.add_argument("--gateway-url", default="", help="Gateway base URL, e.g. http://127.0.0.1:8787")
    p_skills_validate.add_argument("--token", default="", help="Bearer token for protected gateway endpoints")
    p_skills_validate.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    p_skills_validate.set_defaults(handler=cmd_skills_validate, force=True)

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

    p_skills_install = skills_sub.add_parser("install", help="Install a managed skill into the marketplace root")
    p_skills_install.add_argument("slug")
    p_skills_install.set_defaults(handler=cmd_skills_install)

    p_skills_update = skills_sub.add_parser("update", help="Update one managed skill through ClawHub")
    p_skills_update.add_argument("name")
    p_skills_update.set_defaults(handler=cmd_skills_update)

    p_skills_search = skills_sub.add_parser("search", help="Search ClawHub for managed skills")
    p_skills_search.add_argument("query")
    p_skills_search.add_argument("--limit", type=int, default=5)
    p_skills_search.set_defaults(handler=cmd_skills_search)

    p_skills_managed = skills_sub.add_parser("managed", help="List managed marketplace skills discovered locally")
    p_skills_managed.add_argument(
        "--status",
        choices=["ready", "missing_requirements", "policy_blocked", "disabled", "invalid_contract", "unavailable"],
        default="",
        help="Optional managed-skill status filter",
    )
    p_skills_managed.add_argument("--query", default="", help="Optional case-insensitive search filter")
    p_skills_managed.set_defaults(handler=cmd_skills_managed)

    p_skills_sync = skills_sub.add_parser("sync", help="Update managed marketplace skills with ClawHub")
    p_skills_sync.set_defaults(handler=cmd_skills_sync)

    p_skills_remove = skills_sub.add_parser("remove", help="Remove a managed skill from the marketplace root")
    p_skills_remove.add_argument("name")
    p_skills_remove.set_defaults(handler=cmd_skills_remove)

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
        with _temporary_cli_profile(getattr(args, "profile", None)):
            return int(handler(args) or 0)
    except KeyboardInterrupt:
        _print_stderr("error: interrupted")
        return 130
    except (ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
        _print_stderr(_format_cli_error(exc))
        return 2
