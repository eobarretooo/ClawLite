from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import shlex
import shutil
import socket
from pathlib import Path
from urllib.parse import urlparse

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
    _POSIX_SHELL_BINARIES = frozenset({"bash", "dash", "ksh", "sh", "zsh"})
    _WINDOWS_SHELL_BINARIES = frozenset({"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"})
    _POSIX_SHELL_COMMAND_FLAGS = frozenset({"-c", "-lc"})
    _WINDOWS_SHELL_COMMAND_FLAGS = frozenset({"/c", "-c", "-command"})
    _SHELL_PATH_RE = re.compile(
        r"(~(?:[/\\][^\s\"'|><;]+)+|(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[A-Za-z_][A-Za-z0-9_]*%)(?:[/\\][^\s\"'|><;]+)+)"
    )
    _SHELL_CONTROL_TOKENS = frozenset({"&&", "||", "|", ";", "&", ">", ">>", "<", "<<"})
    _NETWORK_FETCH_BINARIES = frozenset({"curl", "wget", "invoke-webrequest", "invoke-restmethod", "iwr", "irm"})
    _HTTP_URL_RE = re.compile(r"https?://[^\s\"'`;|<>)]+", re.IGNORECASE)
    _ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
    _TIMEOUT_DURATION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?(?:[smhd]|ms)?$", re.IGNORECASE)
    _TRANSPARENT_RUNTIME_WRAPPERS = frozenset({"command", "env", "env.exe", "nice", "nohup", "stdbuf", "timeout"})
    _TRANSPARENT_RUNTIME_WRAPPER_FLAGS: dict[str, dict[str, int]] = {
        "command": {"--": 0, "-p": 0, "-v": 0, "-V": 0},
        "env": {
            "--": 0,
            "-i": 0,
            "--ignore-environment": 0,
            "-u": 1,
            "--unset": 1,
            "-c": 1,
            "--chdir": 1,
            "-s": 1,
            "--split-string": 1,
        },
        "nice": {"--": 0, "-n": 1, "--adjustment": 1},
        "nohup": {"--": 0},
        "stdbuf": {"--": 0, "-i": 1, "-o": 1, "-e": 1},
        "timeout": {
            "--": 0,
            "-k": 1,
            "--kill-after": 1,
            "-s": 1,
            "--signal": 1,
            "--foreground": 0,
            "--preserve-status": 0,
            "--verbose": 0,
        },
    }
    _INLINE_RUNTIME_FLAGS: dict[str, frozenset[str]] = {
        "python": frozenset({"-c"}),
        "node": frozenset({"-e", "--eval", "-p", "--print"}),
        "ruby": frozenset({"-e"}),
        "php": frozenset({"-r"}),
        "perl": frozenset({"-e"}),
        "powershell": frozenset({"-c", "-command", "--command"}),
    }
    _PYTHON_NETWORK_MODULES = frozenset({"urllib.request"})
    _INLINE_RUNTIME_NETWORK_HINTS: dict[str, re.Pattern[str]] = {
        "python": re.compile(
            r"(requests\.\w+|httpx\.\w+|urllib\.request\.|urlopen\s*\(|aiohttp\.|urllib3\.|socket\.(?:create_connection|getaddrinfo|socket)\s*\()",
            re.IGNORECASE,
        ),
        "node": re.compile(
            r"(fetch\s*\(|axios\.\w+|http(?:s)?\.(?:get|request)\s*\(|undici|got\s*\()",
            re.IGNORECASE,
        ),
        "ruby": re.compile(r"(Net::HTTP|URI\.open|OpenURI)", re.IGNORECASE),
        "php": re.compile(r"(curl_init\s*\(|file_get_contents\s*\(|stream_socket_client\s*\()", re.IGNORECASE),
        "perl": re.compile(r"(LWP::UserAgent|HTTP::Tiny|getstore\s*\()", re.IGNORECASE),
        "powershell": re.compile(r"(Invoke-WebRequest|Invoke-RestMethod|Net\.Web(?:Client|Request))", re.IGNORECASE),
    }
    _CURL_URL_FLAGS = frozenset({"--url"})
    _CURL_SKIP_VALUE_FLAGS = frozenset({"-x", "--proxy", "-e", "--referer"})
    _POWERSHELL_URL_FLAGS = frozenset({"-uri", "-url"})
    _POWERSHELL_SKIP_VALUE_FLAGS = frozenset({"-proxy"})

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

    @staticmethod
    def _binary_name(raw: object) -> str:
        value = str(raw or "").strip().strip("\"'")
        if not value:
            return ""
        parts = [part for part in re.split(r"[\\/]", value) if part]
        return (parts[-1] if parts else value).lower()

    @classmethod
    def _extract_explicit_shell_command(cls, argv: list[str]) -> str:
        if not argv:
            return ""
        binary = cls._binary_name(argv[0])
        if binary in cls._POSIX_SHELL_BINARIES:
            for index, token in enumerate(argv[1:], start=1):
                if str(token).lower() in cls._POSIX_SHELL_COMMAND_FLAGS and index + 1 < len(argv):
                    return str(argv[index + 1] or "")
            return ""
        if binary == "cmd" or binary == "cmd.exe":
            for index, token in enumerate(argv[1:], start=1):
                if str(token).lower() == "/c" and index + 1 < len(argv):
                    return " ".join(str(item or "") for item in argv[index + 1:])
            return ""
        if binary in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
            for index, token in enumerate(argv[1:], start=1):
                if str(token).lower() in cls._WINDOWS_SHELL_COMMAND_FLAGS and index + 1 < len(argv):
                    return " ".join(str(item or "") for item in argv[index + 1:])
        return ""

    @classmethod
    def _shell_like_paths(cls, command: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for match in cls._SHELL_PATH_RE.findall(str(command or "")):
            value = str(match or "").strip()
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        return out

    @staticmethod
    def _resolve_shell_like_path(raw: str, *, cwd: Path) -> Path | None:
        value = str(raw or "").strip().strip("\"'")
        if not value:
            return None

        candidate: Path | None = None
        if value.startswith("~"):
            suffix = value[1:].lstrip("/\\")
            candidate = Path.home() / suffix if suffix else Path.home()
        elif value.startswith("${"):
            end = value.find("}")
            if end <= 2:
                return None
            variable = value[2:end]
            suffix = value[end + 1 :]
            base = str(cwd) if variable == "PWD" else os.environ.get(variable, "")
            if not base or not suffix.startswith(("/", "\\")):
                return None
            candidate = Path(base) / suffix.lstrip("/\\")
        elif value.startswith("$"):
            match = re.match(r"^\$([A-Za-z_][A-Za-z0-9_]*)(.*)$", value)
            if match is None:
                return None
            variable = match.group(1)
            suffix = match.group(2)
            base = str(cwd) if variable == "PWD" else os.environ.get(variable, "")
            if not base or not suffix.startswith(("/", "\\")):
                return None
            candidate = Path(base) / suffix.lstrip("/\\")
        elif value.startswith("%"):
            match = re.match(r"^%([A-Za-z_][A-Za-z0-9_]*)%(.*)$", value)
            if match is None:
                return None
            variable = match.group(1)
            suffix = match.group(2)
            base = os.environ.get(variable, "")
            if not base or not suffix.startswith(("/", "\\")):
                return None
            candidate = Path(base) / suffix.lstrip("/\\")

        if candidate is None:
            return None
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            return candidate.expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    @classmethod
    def _network_fetch_binary_name(cls, raw: object) -> str:
        value = str(raw or "").strip().strip("\"'")
        if not value:
            return ""
        value = re.sub(r"^[<$({]+", "", value)
        return cls._binary_name(value)

    @staticmethod
    def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
        return (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_private
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )

    @classmethod
    def _validate_network_fetch_url(cls, raw_url: str) -> str | None:
        value = str(raw_url or "").strip()
        if not value:
            return None
        try:
            parsed = urlparse(value)
        except Exception:
            return None
        if parsed.scheme not in {"http", "https"}:
            return None
        host = str(parsed.hostname or "").strip().lower()
        if not host:
            return "blocked_by_policy:internal_url:missing_host"
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
            return f"blocked_by_policy:internal_url:{host}"
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            if cls._is_blocked_ip(literal):
                return f"blocked_by_policy:internal_url:{host}"
            return None
        try:
            infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            return None
        for info in infos:
            try:
                resolved = ipaddress.ip_address(str(info[4][0]))
            except (ValueError, IndexError, TypeError):
                continue
            if cls._is_blocked_ip(resolved):
                return f"blocked_by_policy:internal_url:{host}"
        return None

    @classmethod
    def _iter_network_fetch_segments(cls, argv: list[str]) -> list[tuple[str, list[str]]]:
        segments: list[tuple[str, list[str]]] = []
        active_binary = ""
        active_tokens: list[str] = []
        for raw in argv:
            token = str(raw or "")
            if token in cls._SHELL_CONTROL_TOKENS:
                if active_binary and active_tokens:
                    segments.append((active_binary, active_tokens))
                active_binary = ""
                active_tokens = []
                continue
            if active_binary:
                active_tokens.append(token)
                continue
            binary = cls._network_fetch_binary_name(token)
            if binary in cls._NETWORK_FETCH_BINARIES:
                active_binary = binary
                active_tokens = [token]
        if active_binary and active_tokens:
            segments.append((active_binary, active_tokens))
        return segments

    @classmethod
    def _iter_network_fetch_target_urls(cls, binary: str, tokens: list[str]) -> list[str]:
        urls: list[str] = []
        expect_url = False
        skip_next = False
        for raw in tokens[1:]:
            token = str(raw or "").strip()
            lower = token.lower()
            if not token:
                continue
            if skip_next:
                skip_next = False
                continue
            if expect_url:
                expect_url = False
                urls.append(token)
                continue
            if lower in cls._SHELL_CONTROL_TOKENS:
                break
            if binary == "curl":
                if lower.startswith("--url="):
                    urls.append(token.split("=", 1)[1])
                    continue
                if lower in cls._CURL_URL_FLAGS:
                    expect_url = True
                    continue
                if lower in cls._CURL_SKIP_VALUE_FLAGS:
                    skip_next = True
                    continue
            elif binary in {"invoke-webrequest", "invoke-restmethod", "iwr", "irm"}:
                if lower.startswith("-uri:") or lower.startswith("-url:"):
                    urls.append(token.split(":", 1)[1])
                    continue
                if lower in cls._POWERSHELL_URL_FLAGS:
                    expect_url = True
                    continue
                if lower in cls._POWERSHELL_SKIP_VALUE_FLAGS:
                    skip_next = True
                    continue
            if token.startswith("-"):
                continue
            urls.append(token)
        return urls

    @classmethod
    def _runtime_family(cls, raw: object) -> str:
        binary = cls._binary_name(raw)
        if binary in {"python", "python3", "python.exe", "python3.exe", "py"}:
            return "python"
        if binary in {"node", "node.exe"}:
            return "node"
        if binary in {"ruby", "ruby.exe"}:
            return "ruby"
        if binary in {"php", "php.exe"}:
            return "php"
        if binary in {"perl", "perl.exe"}:
            return "perl"
        if binary in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
            return "powershell"
        return ""

    @classmethod
    def _is_env_assignment(cls, raw: object) -> bool:
        token = str(raw or "").strip()
        return bool(token) and cls._ENV_ASSIGNMENT_RE.match(token) is not None

    @classmethod
    def _transparent_runtime_wrapper_name(cls, raw: object) -> str:
        binary = cls._binary_name(raw)
        if binary in cls._TRANSPARENT_RUNTIME_WRAPPERS:
            return "env" if binary == "env.exe" else binary
        return ""

    @classmethod
    def _transparent_runtime_wrapper_flag_consumption(cls, wrapper: str, raw: object) -> int | None:
        token = str(raw or "").strip()
        lower = token.lower()
        if not lower:
            return None
        spec = cls._TRANSPARENT_RUNTIME_WRAPPER_FLAGS.get(wrapper, {})
        if lower in spec:
            return spec[lower]
        if wrapper == "nice" and lower.startswith("--adjustment="):
            return 0
        if wrapper == "stdbuf":
            if re.match(r"^-[ioe].+$", token, re.IGNORECASE):
                return 0
            if lower.startswith("--input=") or lower.startswith("--output=") or lower.startswith("--error="):
                return 0
        if wrapper == "env":
            if lower.startswith("--unset=") or lower.startswith("--chdir="):
                return 0
        return None

    @classmethod
    def _resolve_inline_runtime_start(cls, argv: list[str]) -> int | None:
        if not argv:
            return None
        index = 0
        while index < len(argv):
            token = str(argv[index] or "").strip()
            if not token:
                index += 1
                continue
            if token in cls._SHELL_CONTROL_TOKENS:
                return None
            if cls._is_env_assignment(token):
                index += 1
                continue
            wrapper = cls._transparent_runtime_wrapper_name(token)
            if not wrapper:
                return index
            index += 1
            while index < len(argv):
                inner = str(argv[index] or "").strip()
                if not inner:
                    index += 1
                    continue
                if inner in cls._SHELL_CONTROL_TOKENS:
                    return None
                if wrapper == "env" and cls._is_env_assignment(inner):
                    index += 1
                    continue
                consumption = cls._transparent_runtime_wrapper_flag_consumption(wrapper, inner)
                if consumption is None:
                    if wrapper == "timeout" and cls._TIMEOUT_DURATION_RE.match(inner) is not None:
                        index += 1
                        continue
                    break
                index += 1 + consumption
            continue
        return None

    @classmethod
    def _inline_runtime_payload(cls, argv: list[str]) -> tuple[str, str] | None:
        start = cls._resolve_inline_runtime_start(argv)
        if start is None or start >= len(argv):
            return None
        runtime = cls._runtime_family(argv[start])
        if not runtime:
            return None
        flags = cls._INLINE_RUNTIME_FLAGS.get(runtime, frozenset())
        if not flags:
            return None
        for index, inner_raw in enumerate(argv[start + 1:], start=start + 1):
            inner = str(inner_raw or "").strip()
            if not inner:
                continue
            if inner in cls._SHELL_CONTROL_TOKENS:
                break
            if inner.lower() in flags and index + 1 < len(argv):
                payload = str(argv[index + 1] or "")
                return runtime, payload
            if not inner.startswith("-"):
                break
        return None

    @classmethod
    def _guard_inline_runtime_fetch_targets(cls, argv: list[str]) -> str | None:
        payload_row = cls._inline_runtime_payload(argv)
        if payload_row is None:
            return None
        runtime, payload = payload_row
        hint_re = cls._INLINE_RUNTIME_NETWORK_HINTS.get(runtime)
        if hint_re is None or hint_re.search(payload) is None:
            return None
        for raw_url in cls._HTTP_URL_RE.findall(payload):
            error = cls._validate_network_fetch_url(raw_url)
            if error:
                return error
        return None

    @classmethod
    def _guard_python_module_fetch_targets(cls, argv: list[str]) -> str | None:
        start = cls._resolve_inline_runtime_start(argv)
        if start is None or start >= len(argv):
            return None
        if cls._runtime_family(argv[start]) != "python":
            return None
        for index, raw in enumerate(argv[start + 1:], start=start + 1):
            token = str(raw or "").strip()
            lower = token.lower()
            if not token:
                continue
            if token in cls._SHELL_CONTROL_TOKENS:
                break
            if lower == "-m" and index + 1 < len(argv):
                module_name = str(argv[index + 1] or "").strip().lower()
                if module_name not in cls._PYTHON_NETWORK_MODULES:
                    return None
                for candidate_raw in argv[index + 2:]:
                    candidate = str(candidate_raw or "").strip()
                    if not candidate:
                        continue
                    if candidate in cls._SHELL_CONTROL_TOKENS:
                        break
                    if candidate == "--":
                        continue
                    if candidate.startswith("-"):
                        continue
                    error = cls._validate_network_fetch_url(candidate)
                    if error:
                        return error
                return None
            if not token.startswith("-"):
                break
        return None

    @classmethod
    def _guard_env_split_string_payloads(cls, argv: list[str], *, recursion_depth: int = 0) -> str | None:
        if recursion_depth >= 4:
            return None
        for index, raw in enumerate(argv):
            if cls._binary_name(raw) != "env":
                continue
            pointer = index + 1
            while pointer < len(argv):
                token = str(argv[pointer] or "").strip()
                lower = token.lower()
                if not token:
                    pointer += 1
                    continue
                if token in cls._SHELL_CONTROL_TOKENS:
                    break
                if cls._is_env_assignment(token):
                    pointer += 1
                    continue
                if lower in {"-s", "--split-string"} and pointer + 1 < len(argv):
                    payload = str(argv[pointer + 1] or "").strip()
                    if not payload:
                        break
                    try:
                        nested_argv = shlex.split(payload)
                    except ValueError:
                        return None
                    return cls._guard_network_fetch_targets(nested_argv, recursion_depth=recursion_depth + 1)
                consumption = cls._transparent_runtime_wrapper_flag_consumption("env", token)
                if consumption is None:
                    break
                pointer += 1 + consumption
        return None

    @classmethod
    def _guard_network_fetch_targets(cls, argv: list[str], *, recursion_depth: int = 0) -> str | None:
        for binary, tokens in cls._iter_network_fetch_segments(argv):
            for raw_url in cls._iter_network_fetch_target_urls(binary, tokens):
                error = cls._validate_network_fetch_url(raw_url)
                if error:
                    return error
        split_string_error = cls._guard_env_split_string_payloads(argv, recursion_depth=recursion_depth)
        if split_string_error:
            return split_string_error
        inline_error = cls._guard_inline_runtime_fetch_targets(argv)
        if inline_error:
            return inline_error
        module_error = cls._guard_python_module_fetch_targets(argv)
        if module_error:
            return module_error
        return None

    def _guard_explicit_shell_command(self, shell_command: str, cwd: Path, *, recursion_depth: int) -> str | None:
        if self.restrict_to_workspace:
            workspace = self.workspace_path
            for raw in self._shell_like_paths(shell_command):
                resolved = self._resolve_shell_like_path(raw, cwd=cwd)
                if resolved is None:
                    return f"blocked_by_workspace_guard:unresolved_shell_path:{raw}"
                if resolved != workspace and workspace not in resolved.parents:
                    return f"blocked_by_workspace_guard:shell_path_outside_workspace:{raw}"
        try:
            nested_argv = shlex.split(shell_command)
        except ValueError:
            return "invalid_command_syntax"
        if not nested_argv or recursion_depth >= 4:
            return None
        return self._guard_command(shell_command, nested_argv, cwd, recursion_depth=recursion_depth + 1)

    def _guard_command(self, command: str, argv: list[str], cwd: Path, *, recursion_depth: int = 0) -> str | None:
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

        shell_command = self._extract_explicit_shell_command(argv)
        if shell_command:
            nested_error = self._guard_explicit_shell_command(shell_command, cwd, recursion_depth=recursion_depth)
            if nested_error:
                return nested_error

        # ᚾ Network guard: block internal fetches in curl/wget/inline runtimes
        network_error = self._guard_network_fetch_targets(argv)
        if network_error:
            try:
                from clawlite.core.runestone import audit as _rs_audit
                _rs_audit(kind="exec_network_block", source="exec", details={"error": network_error, "command": cmd[:256]})
            except Exception:
                pass
            return network_error

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
