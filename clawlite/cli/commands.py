from __future__ import annotations

import argparse
import asyncio
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
from clawlite.cli.ops import memory_privacy_snapshot
from clawlite.cli.ops import memory_profile_snapshot
from clawlite.cli.ops import memory_shared_opt_in
from clawlite.cli.ops import memory_snapshot_create
from clawlite.cli.ops import memory_snapshot_rollback
from clawlite.cli.ops import memory_suggest_snapshot
from clawlite.cli.ops import memory_version_snapshot
from clawlite.cli.ops import memory_doctor_snapshot
from clawlite.cli.ops import onboarding_validation
from clawlite.cli.ops import provider_validation
from clawlite.cli.ops import provider_login_openai_codex
from clawlite.cli.ops import provider_logout_openai_codex
from clawlite.cli.ops import provider_status
from clawlite.cli.ops import provider_use_model
from clawlite.cli.onboarding import run_onboarding_wizard
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


def cmd_start(args: argparse.Namespace) -> int:
    from clawlite.gateway.server import run_gateway

    cfg = _ensure_config_materialized(args.config)
    host = args.host or cfg.gateway.host
    port = args.port or cfg.gateway.port
    run_gateway(host=host, port=port)
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


def cmd_skills_list(args: argparse.Namespace) -> int:
    loader = SkillsLoader()
    rows = loader.discover(include_unavailable=args.all)
    payload = {
        "skills": [
            {
                "name": row.name,
                "description": row.description,
                "always": row.always,
                "source": row.source,
                "available": row.available,
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
    loader = SkillsLoader()
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
    loader = SkillsLoader()
    _print_json(loader.diagnostics_report())
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

    p_status = sub.add_parser("status", help="Show runtime/config status summary")
    p_status.set_defaults(handler=cmd_status)

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

    p_provider = sub.add_parser("provider", help="Provider auth lifecycle commands")
    provider_sub = p_provider.add_subparsers(dest="provider_command", required=True)

    p_provider_login = provider_sub.add_parser("login", help="Login and persist provider auth")
    p_provider_login.add_argument("provider", choices=["openai-codex"])
    p_provider_login.add_argument("--access-token", default="", help="Explicit Codex access token")
    p_provider_login.add_argument("--account-id", default="", help="Optional OpenAI account/org id")
    p_provider_login.add_argument("--set-model", action="store_true", help="Set active model to openai-codex/gpt-5.3-codex")
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
    p_memory_doctor.add_argument("--repair", action="store_true", help="Trigger safe history repair before reporting")
    p_memory_doctor.set_defaults(handler=cmd_memory_doctor)

    p_memory_eval = memory_sub.add_parser("eval", help="Run deterministic synthetic memory retrieval evaluation")
    p_memory_eval.add_argument("--limit", type=int, default=5, help="Top-k retrieval limit per synthetic query")
    p_memory_eval.set_defaults(handler=cmd_memory_eval)

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
    return int(handler(args) or 0)
