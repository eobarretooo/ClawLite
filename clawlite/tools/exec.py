from __future__ import annotations

import asyncio
import os
import re
import shlex
from pathlib import Path

from clawlite.tools.base import Tool, ToolContext
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


class ExecTool(Tool):
    name = "exec"
    description = "Run shell command safely (no shell=True)."

    def __init__(
        self,
        *,
        workspace_path: str | Path | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
        timeout_seconds: int = 60,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        deny_path_patterns: list[str] | None = None,
        allow_path_patterns: list[str] | None = None,
    ) -> None:
        self.workspace_path = (Path(workspace_path).expanduser().resolve() if workspace_path else Path.cwd().resolve())
        self.restrict_to_workspace = bool(restrict_to_workspace)
        self.path_append = str(path_append or "")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.deny_patterns = list(deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",
            r"\bdel\s+/[fq]\b",
            r"\brmdir\s+/s\b",
            r"(?:^|[;&|]\s*)format\b",
            r"\b(mkfs|diskpart)\b",
            r"\bdd\s+if=",
            r">\s*/dev/sd",
            r"\b(shutdown|reboot|poweroff)\b",
            r":\(\)\s*\{.*\};\s*:",
        ])
        self.allow_patterns = [str(pattern) for pattern in (allow_patterns or []) if str(pattern).strip()]
        self.deny_path_patterns = [str(pattern) for pattern in (deny_path_patterns or []) if str(pattern).strip()]
        self.allow_path_patterns = [str(pattern) for pattern in (allow_path_patterns or []) if str(pattern).strip()]

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "default": self.timeout_seconds},
            },
            "required": ["command"],
        }

    @staticmethod
    def _is_windows_absolute_path(raw: str) -> bool:
        return bool(re.match(r"^[A-Za-z]:\\", raw))

    @staticmethod
    def _extract_absolute_paths(command: str) -> list[str]:
        win_paths = re.findall(r"[A-Za-z]:\\[^\s\"'|><;]+", command)
        posix_paths = re.findall(r"(?:^|[\s|>=\"'])(/[^\s\"'|><;]+)", command)
        return win_paths + posix_paths

    @staticmethod
    def _path_like_tokens(argv: list[str]) -> list[str]:
        candidates: list[str] = []
        for token in argv:
            if not token:
                continue
            parts = [token]
            if "=" in token:
                parts.append(token.split("=", 1)[1])
            for part in parts:
                value = part.strip().strip("\"'")
                if not value or "://" in value:
                    continue
                if value == ".." or value.startswith(("../", "..\\", "./", ".\\", "/", "~", "\\")):
                    candidates.append(value)
                    continue
                if "/" in value or "\\" in value:
                    candidates.append(value)
        return candidates

    @staticmethod
    def _match_any(patterns: list[str], value: str) -> bool:
        for pattern in patterns:
            try:
                if re.search(pattern, value, flags=re.IGNORECASE):
                    return True
            except re.error:
                continue
        return False

    def _guard_command(self, command: str, argv: list[str], cwd: Path) -> str | None:
        cmd = command.strip()
        if not cmd:
            return "blocked_by_policy:empty_command"

        if self._match_any(self.deny_patterns, cmd):
            return "blocked_by_policy:deny_pattern"
        if self.allow_patterns and (not self._match_any(self.allow_patterns, cmd)):
            return "blocked_by_policy:not_in_allow_patterns"

        path_candidates = self._path_like_tokens(argv)
        for path_value in path_candidates:
            if self._match_any(self.deny_path_patterns, path_value):
                return f"blocked_by_policy:path_deny_pattern:{path_value}"
            if self.allow_path_patterns and (not self._match_any(self.allow_path_patterns, path_value)):
                return f"blocked_by_policy:path_not_in_allow_patterns:{path_value}"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "blocked_by_workspace_guard:path_traversal"

            workspace = self.workspace_path
            absolute_paths = self._extract_absolute_paths(command)
            for token in argv:
                value = token.strip().strip("\"'")
                if "=" in value:
                    value = value.split("=", 1)[1].strip().strip("\"'")
                if value.startswith("/") or self._is_windows_absolute_path(value):
                    absolute_paths.append(value)

            for raw in absolute_paths:
                value = raw.strip()
                if not value or self._is_windows_absolute_path(value):
                    continue
                try:
                    candidate = Path(value).expanduser().resolve()
                except (OSError, RuntimeError, ValueError):
                    continue
                if candidate != workspace and workspace not in candidate.parents:
                    return f"blocked_by_workspace_guard:path_outside_workspace:{value}"

            for raw in path_candidates:
                value = raw.strip()
                if value.startswith("~"):
                    resolved = (Path.home() / value[1:]).resolve()
                    if resolved != workspace and workspace not in resolved.parents:
                        return f"blocked_by_workspace_guard:path_outside_workspace:{value}"

                if value.startswith(("./", ".\\", "../", "..\\", "..")):
                    try:
                        resolved = (cwd / value).resolve()
                    except (OSError, RuntimeError, ValueError):
                        continue
                    if resolved != workspace and workspace not in resolved.parents:
                        return f"blocked_by_workspace_guard:path_outside_workspace:{value}"

        return None

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        command = str(arguments.get("command", "")).strip()
        log = bind_event("tool.exec", session=ctx.session_id, tool=self.name)
        if not command:
            raise ValueError("command is required")

        timeout = float(arguments.get("timeout", self.timeout_seconds) or self.timeout_seconds)
        argv = shlex.split(command)
        cwd_path = self.workspace_path if self.restrict_to_workspace else Path.cwd().resolve()
        guard_error = self._guard_command(command, argv, cwd_path)
        if guard_error:
            log.warning("command blocked by workspace guard error={}", guard_error)
            return f"exit=-1\nstdout=\nstderr={guard_error}"

        env = os.environ.copy()
        if self.path_append:
            current = env.get("PATH", "")
            env["PATH"] = f"{current}{os.pathsep}{self.path_append}" if current else self.path_append

        cwd = str(self.workspace_path) if self.restrict_to_workspace else None

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except OSError as exc:
            log.error("spawn failed error={}", exc)
            return f"exit=-1\nstdout=\nstderr={exc}"
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            telemetry = [f"timeout_s={timeout}", f"pid={process.pid}", "kill_sent=true"]
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
                telemetry.append("cleanup=wait_ok")
            except asyncio.TimeoutError:
                telemetry.append("cleanup=wait_timeout")
            finally:
                try:
                    await process.communicate()
                    telemetry.append("cleanup=pipes_drained")
                except Exception:
                    telemetry.append("cleanup=pipe_error")
            telemetry_payload = ";".join(telemetry)
            log.warning("command timeout timeout_s={} telemetry={}", timeout, telemetry_payload)
            return f"exit=-1\nstdout=\nstderr=timeout after {timeout}s\ntelemetry={telemetry_payload}"

        stdout = out.decode("utf-8", errors="ignore").strip()
        log.debug("command finished exit_code={}", process.returncode)
        stderr = err.decode("utf-8", errors="ignore").strip()
        return f"exit={process.returncode}\nstdout={stdout}\nstderr={stderr}"
