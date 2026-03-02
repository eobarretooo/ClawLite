from __future__ import annotations

import json
from typing import Any

from clawlite.core.plugin_sdk import HookPhase
from clawlite.core.rbac import Identity, ROLE_SCOPES, Role, check_tool_approval
from clawlite.core.tools import exec_cmd, read_file, write_file


def _default_identity() -> Identity:
    return Identity(
        name="agent-core",
        role=Role.AGENT,
        scopes=set(ROLE_SCOPES[Role.AGENT]),
    )


def _dispatch_skill_tool(name: str, args: dict[str, Any]) -> str:
    from clawlite.mcp import dispatch_skill_tool

    payload = dict(args)
    if name == "cron":
        payload = {"command": str(args.get("command") or args.get("prompt") or "").strip()}
        raw = dispatch_skill_tool("skill.cron", payload)
    else:
        if "command" not in payload and "prompt" in payload:
            payload["command"] = payload.get("prompt")
        raw = dispatch_skill_tool(name, payload)

    content = raw.get("content", []) if isinstance(raw, dict) else []
    parts = [str(item.get("text", "")).strip() for item in content if isinstance(item, dict)]
    return "\n".join([p for p in parts if p]).strip() or json.dumps(raw, ensure_ascii=False)


class ToolExecution:
    def execute_local_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        identity: Identity | None = None,
        plugin_manager: Any | None = None,
        session_id: str = "",
    ) -> str:
        actor = identity or _default_identity()
        allowed, policy = check_tool_approval(name, args, identity=actor)
        if not allowed:
            return f"Ferramenta bloqueada: {policy}"

        result = ""
        try:
            if name == "exec_cmd":
                code, out, err = exec_cmd(str(args.get("command", "")))
                result = f"Exit code {code}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
            elif name == "read_file":
                result = read_file(str(args.get("path", "")))
            elif name == "write_file":
                write_file(str(args.get("path", "")), str(args.get("content", "")))
                result = "Arquivo escrito com sucesso."
            elif name.startswith("browser_"):
                from clawlite.runtime.browser_manager import get_browser_manager

                bm = get_browser_manager()
                if name == "browser_goto":
                    res = bm.goto(str(args.get("url", "")))
                    result = f"{res}\n{bm.get_snapshot()}"
                elif name == "browser_click":
                    res = bm.click(str(args.get("cid", "")))
                    result = f"{res}\n{bm.get_snapshot()}"
                elif name == "browser_fill":
                    res = bm.fill(str(args.get("cid", "")), str(args.get("text", "")))
                    result = f"{res}\n{bm.get_snapshot()}"
                elif name == "browser_press":
                    res = bm.press(str(args.get("key", "")))
                    result = f"{res}\n{bm.get_snapshot()}"
                elif name == "browser_read":
                    result = bm.get_snapshot()
                else:
                    result = f"Erro: ferramenta browser '{name}' nao mapeada."
            elif name == "spawn_subagent":
                from clawlite.runtime.subagents import get_subagent_runtime

                task = str(args.get("task", "")).strip()
                label = str(args.get("label", "")).strip()
                if not task:
                    result = "Erro: argumento 'task' é obrigatório para spawn_subagent."
                else:
                    run = get_subagent_runtime().spawn(
                        session_id=(session_id or "default"),
                        task=task,
                        label=label,
                    )
                    result = json.dumps({"ok": True, "subagent": run}, ensure_ascii=False)
            elif name == "subagents_list":
                from clawlite.runtime.subagents import get_subagent_runtime

                active_only = bool(args.get("active_only", False))
                runs = get_subagent_runtime().list_runs(
                    session_id=(session_id or None),
                    only_active=active_only,
                )
                result = json.dumps({"ok": True, "runs": runs}, ensure_ascii=False)
            elif name == "subagents_kill":
                from clawlite.runtime.subagents import get_subagent_runtime

                runtime = get_subagent_runtime()
                run_id = str(args.get("run_id", "")).strip()
                if run_id:
                    cancelled = runtime.cancel_run(run_id)
                    result = json.dumps({"ok": cancelled, "run_id": run_id}, ensure_ascii=False)
                else:
                    cancelled_count = runtime.cancel_session(session_id or "")
                    result = json.dumps(
                        {"ok": True, "cancelled": cancelled_count, "scope": "session"},
                        ensure_ascii=False,
                    )
            elif name == "cron":
                result = _dispatch_skill_tool("cron", args)
            elif name.startswith("skill."):
                result = _dispatch_skill_tool(name, args)
            else:
                if plugin_manager:
                    plugin_output = plugin_manager.try_execute_tool(name, args)
                    if plugin_output is not None:
                        result = plugin_output
                    else:
                        result = f"Erro: ferramenta '{name}' nao existe."
                else:
                    result = f"Erro: ferramenta '{name}' nao existe."
        except Exception as exc:
            result = f"Erro ao executar a ferramenta: {exc}"

        if plugin_manager:
            try:
                plugin_manager.fire_hooks(
                    HookPhase.AFTER_TOOL_CALL,
                    session_id=session_id,
                    prompt=json.dumps({"tool": name, "arguments": args}, ensure_ascii=False),
                    response=result,
                    metadata={"policy": policy, "tool_name": name},
                )
            except Exception:
                pass
        return result


_TOOL_EXECUTION: ToolExecution | None = None


def get_tool_execution() -> ToolExecution:
    global _TOOL_EXECUTION
    if _TOOL_EXECUTION is None:
        _TOOL_EXECUTION = ToolExecution()
    return _TOOL_EXECUTION

