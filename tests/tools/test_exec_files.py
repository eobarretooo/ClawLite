from __future__ import annotations

import asyncio
import os
import shlex
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from clawlite.tools.exec import ExecTool
from clawlite.tools.files import EditFileTool, EditTool, ListDirTool, ReadFileTool, ReadTool, WriteFileTool, WriteTool
from clawlite.tools.base import ToolContext


def test_exec_tool_runs_command() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run({"command": "echo hello"}, ToolContext(session_id="s"))
        assert "exit=0" in out
        assert "hello" in out

    asyncio.run(_scenario())


@pytest.mark.skipif(os.name == "nt", reason="posix shell operators are covered on unix-like runtimes")
def test_exec_tool_supports_pipe_and_redirect_via_shell_wrapper(tmp_path: Path) -> None:
    async def _scenario() -> None:
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": 'printf "alpha\\nbeta\\n" | tail -n 1 > result.txt && cat result.txt'},
            ToolContext(session_id="s"),
        )
        assert "exit=0" in out
        assert "stdout=beta" in out
        assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "beta\n"

    asyncio.run(_scenario())


def test_file_tools_roundtrip(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "a.txt"
        writer = WriteFileTool()
        reader = ReadFileTool()
        editor = EditFileTool()
        lister = ListDirTool()
        await writer.run({"path": str(target), "content": "hello world"}, ToolContext(session_id="s"))
        text = await reader.run({"path": str(target)}, ToolContext(session_id="s"))
        assert "hello" in text
        changed = await editor.run({"path": str(target), "search": "world", "replace": "claw"}, ToolContext(session_id="s"))
        assert changed == "ok"
        listed = await lister.run({"path": str(tmp_path)}, ToolContext(session_id="s"))
        assert "a.txt" in listed

    asyncio.run(_scenario())


def test_exec_tool_path_append(tmp_path: Path) -> None:
    async def _scenario() -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            script = bin_dir / "hello_from_path_append.cmd"
            script.write_text("@echo off\necho path_append_ok\n", encoding="utf-8", newline="\n")
            command = "hello_from_path_append.cmd"
        else:
            script = bin_dir / "hello_from_path_append"
            script.write_text("#!/usr/bin/env sh\necho path_append_ok\n", encoding="utf-8", newline="\n")
            script.chmod(0o755)
            command = "hello_from_path_append"

        out = await ExecTool(path_append=str(bin_dir)).run(
            {"command": command},
            ToolContext(session_id="s"),
        )
        assert "exit=0" in out
        assert "path_append_ok" in out

    asyncio.run(_scenario())


def test_exec_tool_env_overrides(tmp_path: Path) -> None:
    async def _scenario() -> None:
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": 'python3 -c "import os; print(os.getenv(\'SKILL_TOKEN\', \'\'))"', "env": {"SKILL_TOKEN": "abc123"}},
            ToolContext(session_id="s"),
        )
        assert "exit=0" in out
        assert "abc123" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_dangerous_env_overrides() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": 'python3 -c "print(1)"', "env": {"GIT_SSH_COMMAND": "ssh -i /tmp/key"}},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:env_override:GIT_SSH_COMMAND" in out

    asyncio.run(_scenario())


@pytest.mark.skipif(os.name == "nt", reason="shell wrapper env policy is covered on unix-like runtimes")
def test_exec_tool_blocks_non_allowlisted_env_override_for_shell_wrapper() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "sh -lc 'echo ok'", "env": {"BASH_ENV": "/tmp/pwn.sh"}},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:env_override:BASH_ENV" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_python_env_override_prefix() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": 'python3 -c "print(1)"', "env": {"PYTHONPATH": "/tmp/pwn"}},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:env_override:PYTHONPATH" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_java_tool_options_env_override() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": 'python3 -c "print(1)"', "env": {"JAVA_TOOL_OPTIONS": "-javaagent:/tmp/pwn.jar"}},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:env_override:JAVA_TOOL_OPTIONS" in out

    asyncio.run(_scenario())


@pytest.mark.skipif(os.name == "nt", reason="inline env assignment coverage is unix-specific")
def test_exec_tool_blocks_inline_dangerous_env_assignments() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": '/usr/bin/env BASH_ENV=/tmp/pwn.sh bash -lc "echo hi"'},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:env_override:BASH_ENV" in out

    asyncio.run(_scenario())


@pytest.mark.skipif(os.name == "nt", reason="env split-string coverage is unix-specific")
def test_exec_tool_blocks_split_string_dangerous_env_assignments() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": '/usr/bin/env -S "BASH_ENV=/tmp/pwn.sh bash -lc \'echo hi\'"'},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:env_override:BASH_ENV" in out

    asyncio.run(_scenario())


def test_exec_tool_supports_cwd_override(tmp_path: Path) -> None:
    async def _scenario() -> None:
        subdir = tmp_path / "nested"
        subdir.mkdir(parents=True, exist_ok=True)
        out = await ExecTool().run(
            {"command": 'python3 -c "import os; print(os.getcwd())"', "cwd": str(subdir)},
            ToolContext(session_id="s"),
        )
        assert "exit=0" in out
        assert str(subdir) in out

    asyncio.run(_scenario())


def test_exec_tool_restrict_to_workspace_blocks_cwd_outside_workspace(tmp_path: Path) -> None:
    async def _scenario() -> None:
        outside = tmp_path.parent
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": 'python3 -c "print(1)"', "cwd": str(outside)},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_workspace_guard:cwd_outside_workspace" in out

    asyncio.run(_scenario())


def test_exec_tool_restrict_to_workspace_blocks_outside_path(tmp_path: Path) -> None:
    async def _scenario() -> None:
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": "cat /etc/passwd"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_workspace_guard" in out

    asyncio.run(_scenario())


def test_exec_tool_restrict_to_workspace_blocks_explicit_shell_home_expansion(tmp_path: Path) -> None:
    async def _scenario() -> None:
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": "sh -lc 'cat $HOME/.bashrc'"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_workspace_guard:shell_path_outside_workspace:$HOME/.bashrc" in out

    asyncio.run(_scenario())


def test_exec_tool_restrict_to_workspace_allows_explicit_shell_pwd_inside_workspace(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "inside.txt"
        target.write_text("workspace-ok\n", encoding="utf-8")
        env = {"PWD": str(tmp_path)}
        with patch.dict(os.environ, env, clear=False):
            out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
                {"command": "sh -lc 'cat $PWD/inside.txt'"},
                ToolContext(session_id="s"),
            )
        assert "exit=0" in out
        assert "workspace-ok" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_internal_network_fetch_target() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "curl http://169.254.169.254/latest/meta-data"},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:169.254.169.254" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_metadata_service_ip_outside_builtin_private_sets() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "curl http://100.100.100.200/latest/meta-data"},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:100.100.100.200" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_legacy_ipv4_loopback_literal_in_fetch_command() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "curl http://2130706433/latest/meta-data"},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:2130706433" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_localhost_network_fetch_target() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "wget http://localhost:8000/health"},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:localhost" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_cgnat_resolved_network_fetch_target() -> None:
    command = "curl https://service.example.com/data"
    cgnat_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.64.0.10", 0))]
    with patch("clawlite.tools.exec.socket.getaddrinfo", return_value=cgnat_dns):
        guard_error = ExecTool()._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error == "blocked_by_policy:internal_url:service.example.com"


def test_exec_tool_blocks_internal_network_fetch_inside_shell_composition() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "echo start && curl http://169.254.169.254/latest/meta-data && echo done"},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:169.254.169.254" in out

    asyncio.run(_scenario())


def test_exec_tool_allows_public_fetch_when_local_urls_only_appear_in_proxy_or_payload() -> None:
    tool = ExecTool()
    public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    commands = [
        "curl --proxy http://127.0.0.1:8080 https://example.com",
        "curl https://example.com -H 'Origin: http://localhost:3000'",
        "curl https://example.com --data '{\"callback\":\"http://127.0.0.1:8000/hook\"}'",
    ]
    with patch("clawlite.tools.exec.socket.getaddrinfo", return_value=public_dns):
        for command in commands:
            guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
            assert guard_error is None


def test_exec_tool_blocks_internal_network_fetch_in_python_inline_runtime() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {
                "command": (
                    "python3 -c \"import requests; "
                    "requests.get('http://169.254.169.254/latest/meta-data')\""
                )
            },
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:169.254.169.254" in out

    asyncio.run(_scenario())


def test_exec_tool_blocks_internal_network_fetch_in_env_wrapped_python_inline_runtime() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {
                "command": (
                    "env PYTHONUNBUFFERED=1 python3 -c \"import requests; "
                    "requests.get('http://169.254.169.254/latest/meta-data')\""
                )
            },
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:169.254.169.254" in out

    asyncio.run(_scenario())


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/env python3 -c \"import requests; requests.get('http://169.254.169.254/latest/meta-data')\"",
        "env -i python3 -c \"import requests; requests.get('http://169.254.169.254/latest/meta-data')\"",
        "command -- python3 -c \"import requests; requests.get('http://169.254.169.254/latest/meta-data')\"",
        "nohup python3 -c \"import requests; requests.get('http://169.254.169.254/latest/meta-data')\"",
        "stdbuf -o0 python3 -c \"import requests; requests.get('http://169.254.169.254/latest/meta-data')\"",
        "nice -n 5 python3 -c \"import requests; requests.get('http://169.254.169.254/latest/meta-data')\"",
        "timeout 5 python3 -c \"import requests; requests.get('http://169.254.169.254/latest/meta-data')\"",
    ],
)
def test_exec_tool_blocks_internal_network_fetch_in_transparent_wrapped_inline_runtime(command: str) -> None:
    tool = ExecTool()
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error == "blocked_by_policy:internal_url:169.254.169.254"


def test_exec_tool_blocks_internal_network_fetch_in_env_split_string_direct_fetch() -> None:
    tool = ExecTool()
    command = "/usr/bin/env -S \"curl http://169.254.169.254/latest/meta-data\""
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error == "blocked_by_policy:internal_url:169.254.169.254"


def test_exec_tool_blocks_internal_network_fetch_in_env_split_string_inline_runtime() -> None:
    tool = ExecTool()
    command = (
        "env -S \"python3 -c \\\"import requests; "
        "requests.get('http://169.254.169.254/latest/meta-data')\\\"\""
    )
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error == "blocked_by_policy:internal_url:169.254.169.254"


def test_exec_tool_blocks_internal_network_fetch_in_node_print_inline_runtime() -> None:
    tool = ExecTool()
    command = "node -p \"fetch('http://169.254.169.254/latest/meta-data')\""
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error == "blocked_by_policy:internal_url:169.254.169.254"


def test_exec_tool_blocks_internal_network_fetch_in_python_module_runtime() -> None:
    tool = ExecTool()
    command = "python3 -m urllib.request http://169.254.169.254/latest/meta-data"
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error == "blocked_by_policy:internal_url:169.254.169.254"


def test_exec_tool_blocks_internal_network_fetch_in_env_wrapped_python_module_runtime() -> None:
    tool = ExecTool()
    command = "env -i python3 -m urllib.request http://169.254.169.254/latest/meta-data"
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error == "blocked_by_policy:internal_url:169.254.169.254"


def test_exec_tool_blocks_localhost_network_fetch_in_node_inline_runtime() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "node -e \"fetch('http://localhost:3000/health')\""},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=blocked_by_policy:internal_url:localhost" in out

    asyncio.run(_scenario())


def test_exec_tool_allows_inline_runtime_url_string_without_network_hint() -> None:
    tool = ExecTool()
    command = "python3 -c \"print('http://localhost:8000/health')\""
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error is None


def test_exec_tool_allows_urllib_parse_without_network_call() -> None:
    tool = ExecTool()
    command = (
        "python3 -c \"import urllib.parse; "
        "print(urllib.parse.urlparse('http://localhost:8000/health'))\""
    )
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error is None


def test_exec_tool_allows_print_only_url_in_transparent_wrapped_inline_runtime() -> None:
    tool = ExecTool()
    command = "env -i python3 -c \"print('http://localhost:8000/health')\""
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error is None


def test_exec_tool_allows_print_only_url_in_env_split_string_runtime() -> None:
    tool = ExecTool()
    command = "env -S \"python3 -c \\\"print('http://localhost:8000/health')\\\"\""
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error is None


def test_exec_tool_allows_non_network_python_module_runtime() -> None:
    tool = ExecTool()
    command = "python3 -m urllib.parse http://localhost:8000/health"
    guard_error = tool._guard_command(command, shlex.split(command), Path.cwd().resolve())
    assert guard_error is None


def test_exec_tool_default_policy_blocks_dangerous_command() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "rm -rf /tmp/safe-check"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_policy:deny_pattern" in out

    asyncio.run(_scenario())


def test_exec_tool_allow_patterns_enforced() -> None:
    async def _scenario() -> None:
        out = await ExecTool(allow_patterns=[r"^echo\\s+"]).run(
            {"command": "pwd"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_policy:not_in_allow_patterns" in out

    asyncio.run(_scenario())


def test_exec_tool_restrict_to_workspace_blocks_absolute_path_in_flag(tmp_path: Path) -> None:
    async def _scenario() -> None:
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": "echo done --output=/etc/passwd"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_workspace_guard:path_outside_workspace:/etc/passwd" in out

    asyncio.run(_scenario())


def test_exec_tool_timeout_reports_telemetry() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": 'sh -c "sleep 2"', "timeout": 0.1},
            ToolContext(session_id="s"),
        )
        assert "stderr=timeout after 0.1s" in out
        assert "telemetry=timeout_s=0.1" in out
        assert "kill_sent=true" in out

    asyncio.run(_scenario())


def test_exec_tool_invalid_command_syntax_returns_deterministic_marker() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": 'echo "unterminated'},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=invalid_command_syntax" in out

    asyncio.run(_scenario())


def test_exec_tool_output_truncation_telemetry_for_stdout_and_stderr() -> None:
    async def _scenario() -> None:
        out = await ExecTool(max_output_chars=256).run(
            {
                "command": "python3 -c \"import sys; print('a' * 1200); sys.stderr.write('b' * 1300)\"",
                "max_output_chars": 256,
            },
            ToolContext(session_id="s"),
        )
        assert "exit=0" in out
        assert "stdout_truncated=true" in out
        assert "stderr_truncated=true" in out
        assert "stdout_original_chars=1200" in out
        assert "stderr_original_chars=1300" in out

    asyncio.run(_scenario())


def test_file_tools_restrict_to_workspace_blocks_outside_path(tmp_path: Path) -> None:
    async def _scenario() -> None:
        outside = tmp_path.parent / "outside.txt"
        writer = WriteFileTool(workspace_path=tmp_path, restrict_to_workspace=True)
        with pytest.raises(PermissionError):
            await writer.run({"path": str(outside), "content": "x"}, ToolContext(session_id="s"))

    asyncio.run(_scenario())


def test_file_alias_tools_reuse_existing_behavior(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "alias.txt"
        writer = WriteTool()
        reader = ReadTool()
        editor = EditTool()

        assert writer.name == "write"
        assert reader.name == "read"
        assert editor.name == "edit"

        await writer.run({"path": str(target), "content": "hello alias"}, ToolContext(session_id="s"))
        content = await reader.run({"path": str(target)}, ToolContext(session_id="s"))
        assert content == "hello alias"
        changed = await editor.run(
            {"path": str(target), "search": "alias", "replace": "tool"},
            ToolContext(session_id="s"),
        )
        assert changed == "ok"
        updated = await reader.run({"path": str(target)}, ToolContext(session_id="s"))
        assert updated == "hello tool"

    asyncio.run(_scenario())
