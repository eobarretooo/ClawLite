from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from clawlite.config.loader import load_config
from clawlite.core.skills import SkillsLoader
from clawlite.gateway.server import build_runtime, run_gateway
from clawlite.workspace.loader import WorkspaceLoader


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_start(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    host = args.host or cfg.gateway.host
    port = args.port or cfg.gateway.port
    run_gateway(host=host, port=port)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    runtime = build_runtime(cfg)

    async def _scenario() -> None:
        out = await runtime.engine.run(session_id=args.session_id, user_text=args.prompt)
        _print_json({"text": out.text, "model": out.model})

    asyncio.run(_scenario())
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
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


def cmd_cron_add(args: argparse.Namespace) -> int:
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
    cfg = load_config(args.config)
    runtime = build_runtime(cfg)
    rows = runtime.cron.list_jobs(session_id=args.session_id)
    _print_json({"jobs": rows})
    return 0


def cmd_cron_remove(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    runtime = build_runtime(cfg)
    ok = runtime.cron.remove_job(args.job_id)
    _print_json({"ok": ok})
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawlite", description="ClawLite autonomous assistant CLI")
    parser.add_argument("--config", default=None, help="Path to config JSON/YAML")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start FastAPI gateway")
    p_start.add_argument("--host", default=None)
    p_start.add_argument("--port", type=int, default=None)
    p_start.set_defaults(handler=cmd_start)

    p_run = sub.add_parser("run", help="Run one prompt through the agent engine")
    p_run.add_argument("prompt")
    p_run.add_argument("--session-id", default="cli:default")
    p_run.set_defaults(handler=cmd_run)

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
    p_onboard.set_defaults(handler=cmd_onboard)

    p_cron = sub.add_parser("cron", help="Manage scheduled jobs")
    cron_sub = p_cron.add_subparsers(dest="cron_command", required=True)

    p_cron_add = cron_sub.add_parser("add", help="Add cron job")
    p_cron_add.add_argument("--session-id", required=True)
    p_cron_add.add_argument("--expression", required=True, help="every 60 | at 2026-03-02T12:00:00+00:00 | cron expr")
    p_cron_add.add_argument("--prompt", required=True)
    p_cron_add.add_argument("--name", default="")
    p_cron_add.set_defaults(handler=cmd_cron_add)

    p_cron_list = cron_sub.add_parser("list", help="List jobs for a session")
    p_cron_list.add_argument("--session-id", required=True)
    p_cron_list.set_defaults(handler=cmd_cron_list)

    p_cron_remove = cron_sub.add_parser("remove", help="Remove job by id")
    p_cron_remove.add_argument("--job-id", required=True)
    p_cron_remove.set_defaults(handler=cmd_cron_remove)

    p_skills = sub.add_parser("skills", help="Inspect available skills")
    skills_sub = p_skills.add_subparsers(dest="skills_command", required=True)

    p_skills_list = skills_sub.add_parser("list", help="List skills")
    p_skills_list.add_argument("--all", action="store_true", help="Include unavailable skills")
    p_skills_list.set_defaults(handler=cmd_skills_list)

    p_skills_show = skills_sub.add_parser("show", help="Show one skill body + metadata")
    p_skills_show.add_argument("name")
    p_skills_show.set_defaults(handler=cmd_skills_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if not callable(handler):
        parser.print_help()
        return 1
    return int(handler(args) or 0)
