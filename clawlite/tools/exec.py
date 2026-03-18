from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
from pathlib import Path

import time
from clawlite.tools.base import Tool, ToolContext, ToolHealthResult
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


class ExecTool(Tool):
    name = "exec"
    description = "Run shell command safely (no shell=True)."
    DEFAULT_MAX_OUTPUT_CHARS = 65536
    MIN_MAX_OUTPUT_CHARS = 1024
    MAX_MAX_OUTPUT_CHARS = 1000000
    _WINDOWS_CMD_BUILTINS = {
        "assoc",
        "cd",
        "cls",
        "copy",
        "date",
        "del",
        "dir",
        "echo",
        "erase",
        "md",
        "mkdir",
        "move",
        "rd",
        "ren",
        "rename",
        "rmdir",
        "set",
        "time",
        "type",
        "ver",
        "vol",
    }
    _SHELL_META_RE = re.compile(r"(^|[^\\])(?:\|\||&&|[|<>;`])")
    _ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    _BLOCKED_ENV_OVERRIDE_EXACT = {
        "BROWSER",
        "EDITOR",
        "GIT_EXTERNAL_DIFF",
        "GIT_SSH_COMMAND",
        "NODE_OPTIONS",
        "PAGER",
        "PATH",
        "PS4",
        "RUBYOPT",
        "SHELLOPTS",
        "VISUAL",
    }
    _BLOCKED_ENV_OVERRIDE_PREFIXES = (
        "DYLD_",
        "GIT_CONFIG_",
        "LD_",
        "NPM_CONFIG_",
    )

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
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
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
        self.max_output_chars = self._clamp_max_output_chars(max_output_chars)

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "default": self.timeout_seconds},
                "max_output_chars": {"type": "integer", "default": self.max_output_chars},
                "maxOutputChars": {"type": "integer"},
                "cwd": {"type": "string"},
                "workdir": {"type": "string"},
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["command"],
        }

    @classmethod
    def _clamp_max_output_chars(cls, value: object) -> int:
        try:
            resolved = int(float(value))
        except (TypeError, ValueError):
            resolved = cls.DEFAULT_MAX_OUTPUT_CHARS
        resolved = max(cls.MIN_MAX_OUTPUT_CHARS, resolved)
        return min(cls.MAX_MAX_OUTPUT_CHARS, resolved)

    @staticmethod
    def _truncate_output(value: str, max_chars: int) -> tuple[str, bool, int]:
        original_len = len(value)
        if original_len <= max_chars:
            return value, False, original_len
        return value[:max_chars], True, original_len

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

    @classmethod
    def _normalize_env_overrides(cls, raw: object) -> tuple[dict[str, str], str | None]:
        if raw is None:
            return {}, None
        if not isinstance(raw, dict):
            return {}, "invalid_env_overrides"
        overrides: dict[str, str] = {}
        for key, value in raw.items():
            env_key = str(key or "").strip()
            if not cls._ENV_NAME_RE.fullmatch(env_key):
                return {}, f"invalid_env_name:{env_key or 'empty'}"
            upper_key = env_key.upper()
            if upper_key in cls._BLOCKED_ENV_OVERRIDE_EXACT or any(
                upper_key.startswith(prefix) for prefix in cls._BLOCKED_ENV_OVERRIDE_PREFIXES
            ):
                return {}, f"blocked_by_policy:env_override:{env_key}"
            env_value = str(value or "")
            if "\x00" in env_value or "\n" in env_value or "\r" in env_value:
                return {}, f"invalid_env_value:{env_key}"
            overrides[env_key] = env_value
        return overrides, None

    def _resolve_cwd(self, raw: object) -> tuple[Path | None, str | None]:
        text = str(raw or "").strip()
        if not text:
            if self.restrict_to_workspace:
                return self.workspace_path, None
            return None, None

        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            base = self.workspace_path if self.restrict_to_workspace else Path.cwd().resolve()
            candidate = base / candidate
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            return None, f"invalid_cwd:{text}"
        if not resolved.exists() or not resolved.is_dir():
            return None, f"invalid_cwd:{text}"
        if self.restrict_to_workspace and resolved != self.workspace_path and self.workspace_path not in resolved.parents:
            return None, f"blocked_by_workspace_guard:cwd_outside_workspace:{text}"
        return resolved, None

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

    @staticmethod
    def _normalize_windows_command(command: str, env_path: str) -> tuple[list[str], str]:
        resolved_command = str(command or "")
        argv = shlex.split(resolved_command)
        if argv and argv[0] == "python3":
            python3_path = shutil.which("python3", path=env_path)
            if python3_path is None:
                python_path = shutil.which("python", path=env_path)
                if python_path:
                    argv[0] = python_path
                    resolved_command = re.sub(
                        r"^\s*python3\b",
                        "python",
                        resolved_command,
                        count=1,
                    )
        return argv, resolved_command

    @staticmethod
    def _resolve_windows_path_command(raw_command: str, env_path: str) -> Path | None:
        command_name = str(raw_command or "").strip()
        if not command_name:
            return None
        candidate = Path(command_name)
        if candidate.is_absolute() or any(sep in command_name for sep in ("/", "\\")):
            return candidate if candidate.exists() else None
        for entry in [item for item in env_path.split(os.pathsep) if item]:
            candidate = Path(entry) / command_name
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _bash_compatible_path(path: Path) -> str:
        value = path.resolve().as_posix()
        if re.match(r"^[A-Za-z]:/", value):
            return f"/{value[0].lower()}/{value[3:]}"
        return value

    @classmethod
    def _needs_shell_wrapper(cls, command: str) -> bool:
        value = str(command or "")
        if not value.strip():
            return False
        if cls._SHELL_META_RE.search(value):
            return True
        return "$(" in value

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        command = str(arguments.get("command", "")).strip()
        log = bind_event("tool.exec", session=ctx.session_id, tool=self.name)
        if not command:
            raise ValueError("command is required")

        timeout = float(arguments.get("timeout", self.timeout_seconds) or self.timeout_seconds)
        max_output_chars = self._clamp_max_output_chars(
            arguments.get("max_output_chars", arguments.get("maxOutputChars", self.max_output_chars))
        )
        try:
            argv = shlex.split(command)
        except ValueError:
            log.warning("invalid command syntax blocked")
            return "exit=-1\nstdout=\nstderr=invalid_command_syntax"
        resolved_cwd, cwd_error = self._resolve_cwd(arguments.get("cwd", arguments.get("workdir")))
        if cwd_error:
            log.warning("command blocked by invalid cwd error={}", cwd_error)
            return f"exit=-1\nstdout=\nstderr={cwd_error}"
        cwd_path = resolved_cwd if resolved_cwd is not None else Path.cwd().resolve()
        guard_error = self._guard_command(command, argv, cwd_path)
        if guard_error:
            log.warning("command blocked by workspace guard error={}", guard_error)
            return f"exit=-1\nstdout=\nstderr={guard_error}"

        env = os.environ.copy()
        env_overrides, env_error = self._normalize_env_overrides(arguments.get("env"))
        if env_error:
            log.warning("command blocked by invalid env overrides error={}", env_error)
            return f"exit=-1\nstdout=\nstderr={env_error}"
        env.update(env_overrides)
        if self.path_append:
            current = env.get("PATH", "")
            env["PATH"] = f"{current}{os.pathsep}{self.path_append}" if current else self.path_append
        env_path = str(env.get("PATH", "") or "")

        bash_path = shutil.which("bash", path=env_path) if os.name == "nt" else None
        shell_path = None if os.name == "nt" else (shutil.which("bash", path=env_path) or shutil.which("sh", path=env_path))
        use_shell_wrapper = os.name != "nt" and self._needs_shell_wrapper(command)
        exec_argv = list(argv)
        shell_command = command
        if os.name == "nt":
            try:
                exec_argv, shell_command = self._normalize_windows_command(command, env_path)
            except ValueError:
                log.warning("invalid command syntax blocked")
                return "exit=-1\nstdout=\nstderr=invalid_command_syntax"
        resolved_path_command = (
            self._resolve_windows_path_command(exec_argv[0], env_path)
            if os.name == "nt" and exec_argv
            else None
        )

        cwd = str(cwd_path) if resolved_cwd is not None else None

        try:
            if use_shell_wrapper and shell_path:
                process = await asyncio.create_subprocess_exec(
                    shell_path,
                    "-lc",
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *exec_argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )
        except OSError as exc:
            if os.name == "nt":
                cmd_path = os.environ.get("COMSPEC", "").strip() or shutil.which("cmd", path=env_path)
                command_name = str(exec_argv[0] if exec_argv else "").strip().lower()
                suffix = str(resolved_path_command.suffix).lower() if resolved_path_command is not None else ""
                use_cmd = bool(
                    cmd_path
                    and (
                        command_name in self._WINDOWS_CMD_BUILTINS
                        or suffix in {".cmd", ".bat"}
                    )
                )
                try:
                    if use_cmd and cmd_path:
                        process = await asyncio.create_subprocess_exec(
                            cmd_path,
                            "/d",
                            "/s",
                            "/c",
                            shell_command,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=cwd,
                            env=env,
                        )
                    elif bash_path:
                        if resolved_path_command is not None:
                            process = await asyncio.create_subprocess_exec(
                                bash_path,
                                self._bash_compatible_path(resolved_path_command),
                                *exec_argv[1:],
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                                cwd=cwd,
                                env=env,
                            )
                        else:
                            process = await asyncio.create_subprocess_exec(
                                bash_path,
                                "-lc",
                                shell_command,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                                cwd=cwd,
                                env=env,
                            )
                    else:
                        raise exc
                except OSError as shell_exc:
                    log.error("spawn failed error={}", shell_exc)
                    return f"exit=-1\nstdout=\nstderr={shell_exc}"
            else:
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
        stdout, stdout_truncated, stdout_original_len = self._truncate_output(stdout, max_output_chars)
        stderr, stderr_truncated, stderr_original_len = self._truncate_output(stderr, max_output_chars)
        response = f"exit={process.returncode}\nstdout={stdout}\nstderr={stderr}"
        if stdout_truncated:
            response += f"\nstdout_truncated=true\nstdout_original_chars={stdout_original_len}"
        if stderr_truncated:
            response += f"\nstderr_truncated=true\nstderr_original_chars={stderr_original_len}"
        return response

    async def health_check(self) -> ToolHealthResult:
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                "echo", "ok",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            ok = proc.returncode == 0 and b"ok" in out
            return ToolHealthResult(ok=ok, latency_ms=(time.monotonic() - t0) * 1000, detail="exec_ok" if ok else "unexpected_output")
        except Exception as exc:
            return ToolHealthResult(ok=False, latency_ms=(time.monotonic() - t0) * 1000, detail=str(exc))
