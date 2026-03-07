from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from clawlite.providers.base import LLMResult
from clawlite.config.schema import ToolSafetyPolicyConfig
from clawlite.core.skills import SkillsLoader
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry
from clawlite.tools.skill import SkillTool


class FakeWebSearchTool(Tool):
    name = "web_search"
    description = "fake web search"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"query": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return f"query:{arguments.get('query', '')}:{ctx.session_id}:{ctx.channel}:{ctx.user_id}"


class FakeExecTool(Tool):
    name = "exec"
    description = "fake exec"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return f"exec:{arguments.get('command', '')}:{ctx.channel}:{ctx.user_id}"


class FakeExecStatusTool(Tool):
    name = "exec"
    description = "fake exec with explicit status"

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        del ctx
        command = str(arguments.get("command", "") or "")
        return self.responses.get(command, f"exit=0\nstdout={command}\nstderr=")


class FakeWebFetchPayloadTool(Tool):
    name = "web_fetch"
    description = "fake web fetch"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"url": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        del ctx
        url = str(arguments.get("url", "") or "")
        return json.dumps(
            {
                "ok": True,
                "tool": "web_fetch",
                "result": {"text": f"Fetched content from {url}"},
            }
        )


class FakeReadTool(Tool):
    name = "read"
    description = "fake read"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"path": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        del ctx
        return f"Local content from {arguments.get('path', '')}"


class FakeSessionsSpawnTool(Tool):
    name = "sessions_spawn"
    description = "fake sessions spawn"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"task": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return json.dumps(
            {
                "status": "ok",
                "session_id": ctx.session_id,
                "user_id": ctx.user_id,
                "task": arguments.get("task", ""),
                "tasks": arguments.get("tasks", []),
                "share_scope": arguments.get("share_scope", ""),
            }
        )


class FakeProvider:
    async def complete(self, *, messages, tools, max_tokens=None, temperature=None, reasoning_effort=None):
        del tools, max_tokens, temperature, reasoning_effort
        return LLMResult(model="fake/summary", text=f"summary::{messages[-1]['content'].splitlines()[1]}")


class FakeMemory:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    def integration_policy(self, kind: str, *, session_id: str):
        self.calls.append((kind, session_id))
        return self.verdict


class ExplodingMemory:
    def integration_policy(self, kind: str, *, session_id: str):
        del kind, session_id
        raise RuntimeError("policy backend unavailable")


def _write_skill(root: Path, slug: str, frontmatter: str, body: str = "body") -> None:
    skill_dir = root / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")


def test_run_skill_executes_command_binding(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        'name: echo-skill\ndescription: echo\nalways: false\ncommand: echo',
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeExecTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        reg.register(tool)
        out = await tool.run(
            {"name": "echo-skill", "input": "hello world"},
            ToolContext(session_id="s1"),
        )
        assert out == "exec:echo hello world::"

    asyncio.run(_scenario())


def test_run_skill_respects_unavailable_requirements(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "blocked",
        'name: blocked\ndescription: blocked\nmetadata: {"nanobot":{"requires":{"bins":["definitely-missing-bin-xyz"]}}}',
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run({"name": "blocked"}, ToolContext(session_id="s2"))
        assert out.startswith("skill_unavailable:blocked")

    asyncio.run(_scenario())


def test_run_skill_blocks_disabled_skill(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeExecTool())
        loader = SkillsLoader(builtin_root=tmp_path, state_path=tmp_path / "skills-state.json")
        loader.set_enabled("echo-skill", False)
        tool = SkillTool(loader=loader, registry=reg)
        out = await tool.run(
            {"name": "echo-skill", "input": "hello"},
            ToolContext(session_id="s-disabled"),
        )
        assert out == "skill_disabled:echo-skill"

    asyncio.run(_scenario())


def test_run_skill_dispatches_script_to_tool_registry(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "web",
        "name: web\ndescription: web\nscript: web_search",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeWebSearchTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        reg.register(tool)
        out = await tool.run(
            {"name": "web", "query": "nanobot"},
            ToolContext(session_id="s3", channel="cli", user_id="u3"),
        )
        assert out == "query:nanobot:s3:cli:u3"

    asyncio.run(_scenario())


def test_run_skill_script_respects_channel_safety_policy(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "web",
        "name: web\ndescription: web\nscript: web_search",
    )

    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["web_search"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(FakeWebSearchTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        reg.register(tool)
        out = await tool.run(
            {"name": "web", "query": "nanobot"},
            ToolContext(session_id="s3", channel="telegram", user_id="u3"),
        )
        assert out == "skill_blocked:web:tool_blocked_by_safety_policy:web_search:telegram"

    asyncio.run(_scenario())


def test_run_skill_returns_not_executable_when_no_binding(tmp_path: Path) -> None:
    _write_skill(tmp_path, "doc-only", "name: doc-only\ndescription: doc only")

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run({"name": "doc-only"}, ToolContext(session_id="s4"))
        assert out == "skill_not_executable:doc-only"

    asyncio.run(_scenario())


def test_run_skill_does_not_fallback_to_external_script_exec(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "external-script",
        "name: external-script\ndescription: external\nscript: external_tool",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run({"name": "external-script"}, ToolContext(session_id="s5"))
        assert out == "skill_script_unavailable:external_tool"

    asyncio.run(_scenario())


def test_run_skill_blocks_oversized_argument_list(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {"name": "echo-skill", "args": [str(i) for i in range(33)]},
            ToolContext(session_id="s6"),
        )
        assert out == "skill_blocked:echo-skill:skill_args_exceeded:max=32"

    asyncio.run(_scenario())


def test_run_skill_blocks_command_when_exec_tool_not_registered(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "dangerous",
        "name: dangerous\ndescription: dangerous\ncommand: rm",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {"name": "dangerous", "args": ["-rf", "/"]},
            ToolContext(session_id="s7", channel="cli", user_id="u1"),
        )
        assert out == "skill_blocked:dangerous:exec_tool_not_registered"

    asyncio.run(_scenario())


def test_run_skill_returns_skill_blocked_when_registry_blocks_exec(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(FakeExecTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {"name": "echo-skill", "args": ["hello"]},
            ToolContext(session_id="telegram:skill", channel="telegram", user_id="42"),
        )
        assert out == "skill_blocked:echo-skill:tool_blocked_by_safety_policy:exec:telegram"

    asyncio.run(_scenario())


def test_run_skill_returns_skill_blocked_when_registry_blocks_exec_unknown_channel(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(FakeExecTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {"name": "echo-skill", "args": ["hello"]},
            ToolContext(session_id="skill", channel="", user_id="42"),
        )
        assert out == "skill_blocked:echo-skill:tool_blocked_by_safety_policy:exec:unknown"

    asyncio.run(_scenario())


def test_run_skill_command_uses_exec_tool_in_cli_context(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeExecTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {"name": "echo-skill", "args": ["hello world"]},
            ToolContext(session_id="cli:skill", channel="cli", user_id="7"),
        )
        assert out == "exec:echo 'hello world':cli:7"

    asyncio.run(_scenario())


def test_run_skill_command_prefix_dispatches_multiword_binding(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "gh-issues",
        "name: gh-issues\ndescription: gh issue wrapper\ncommand: gh issue",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeExecTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {"name": "gh-issues", "args": ["list", "--repo", "openclaw/openclaw", "--limit", "5"]},
            ToolContext(session_id="cli:gh-issues", channel="cli", user_id="11"),
        )
        assert out == "exec:gh issue list --repo openclaw/openclaw --limit 5:cli:11"

    asyncio.run(_scenario())


def test_run_skill_allows_execution_when_memory_policy_allows(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeExecTool())
        memory = FakeMemory({"allowed": True})
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg, memory=memory)
        out = await tool.run(
            {"name": "echo-skill", "input": "hello"},
            ToolContext(session_id="s8"),
        )
        assert out == "exec:echo hello::"
        assert memory.calls == [("skill", "s8")]

    asyncio.run(_scenario())


def test_run_skill_blocks_execution_when_memory_policy_denies(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        memory = FakeMemory({"allowed": False, "reason": "maintenance"})
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg, memory=memory)
        out = await tool.run(
            {"name": "echo-skill", "input": "hello"},
            ToolContext(session_id="s9"),
        )
        assert out == "skill_blocked:echo-skill:memory_policy:maintenance"
        assert memory.calls == [("skill", "s9")]

    asyncio.run(_scenario())


def test_run_skill_blocks_execution_when_memory_policy_errors(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeExecTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg, memory=ExplodingMemory())
        out = await tool.run(
            {"name": "echo-skill", "input": "hello"},
            ToolContext(session_id="s10"),
        )
        assert out == "skill_blocked:echo-skill:memory_policy:policy_exception:runtimeerror"

    asyncio.run(_scenario())


def test_run_skill_github_precheck_blocks_when_auth_is_missing(tmp_path: Path, monkeypatch) -> None:
    _write_skill(
        tmp_path,
        "github",
        "name: github\ndescription: github\ncommand: gh issue",
    )

    async def _scenario() -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        reg = ToolRegistry()
        reg.register(
            FakeExecStatusTool(
                {
                    "gh auth status": "exit=1\nstdout=\nstderr=not logged into any GitHub hosts",
                }
            )
        )
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {"name": "github", "args": ["list"]},
            ToolContext(session_id="cli:github", channel="cli", user_id="11"),
        )
        assert out == "skill_auth_required:github:gh:not logged into any GitHub hosts"

    asyncio.run(_scenario())


def test_run_skill_summarize_falls_back_to_provider_for_urls(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "summarize",
        "name: summarize\ndescription: summarize\nscript: summarize",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeWebFetchPayloadTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg, provider=FakeProvider())
        out = await tool.run(
            {"name": "summarize", "input": "https://example.com"},
            ToolContext(session_id="cli:summarize", channel="cli", user_id="42"),
        )
        assert out.startswith("summary::Source: https://example.com")

    asyncio.run(_scenario())


def test_run_skill_summarize_falls_back_to_provider_for_local_files(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "summarize",
        "name: summarize\ndescription: summarize\nscript: summarize",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeReadTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg, provider=FakeProvider())
        out = await tool.run(
            {"name": "summarize", "input": "/tmp/demo.txt"},
            ToolContext(session_id="cli:summarize", channel="cli", user_id="42"),
        )
        assert out.startswith("summary::Source: /tmp/demo.txt")

    asyncio.run(_scenario())


def test_run_skill_weather_falls_back_to_open_meteo(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "weather",
        "name: weather\ndescription: weather\nscript: weather",
    )

    class _Response:
        def __init__(self, text: str, *, status_code: int = 200) -> None:
            self.text = text
            self.status_code = status_code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status={self.status_code}")

        def json(self):
            return json.loads(self.text)

    class _Client:
        def __init__(self, responses: list[_Response], **_: object) -> None:
            self._responses = responses

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params=None):
            del url, params
            if not self._responses:
                raise RuntimeError("no response")
            return self._responses.pop(0)

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        responses = [
            _Response("wttr unavailable", status_code=503),
            _Response(json.dumps({"results": [{"name": "Lisbon", "country": "Portugal", "latitude": 38.72, "longitude": -9.13}]})),
            _Response(json.dumps({"current_weather": {"temperature": 19.5, "windspeed": 12.0, "weathercode": 2}})),
        ]
        with patch("httpx.AsyncClient", side_effect=lambda **kwargs: _Client(responses, **kwargs)):
            out = await tool.run({"name": "weather", "location": "Lisbon"}, ToolContext(session_id="cli:weather"))
            assert out == "Lisbon, Portugal: 19.5°C, partly cloudy, wind 12.0 km/h"

    asyncio.run(_scenario())


def test_run_skill_coding_agent_wraps_sessions_spawn(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "coding-agent",
        "name: coding-agent\ndescription: coding\nscript: coding_agent",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(FakeSessionsSpawnTool())
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {
                "name": "coding-agent",
                "tool_arguments": {"task": "Fix test suite", "share_scope": "family"},
            },
            ToolContext(session_id="cli:coding", channel="cli", user_id="7"),
        )
        payload = json.loads(out)
        assert payload["status"] == "ok"
        assert payload["task"] == "Fix test suite"
        assert payload["share_scope"] == "family"
        assert payload["session_id"] == "cli:coding"

    asyncio.run(_scenario())


def test_run_skill_healthcheck_returns_local_diagnostics_snapshot(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "healthcheck",
        "name: healthcheck\ndescription: health\nscript: healthcheck",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
            }
        ),
        encoding="utf-8",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {
                "name": "healthcheck",
                "tool_arguments": {"config": str(config_path)},
            },
            ToolContext(session_id="cli:health", channel="cli", user_id="7"),
        )
        payload = json.loads(out)
        assert payload["workspace_path"] == str(tmp_path / "workspace")
        assert "validation" in payload
        assert "provider" in payload["validation"]
        assert "channels" in payload["validation"]

    asyncio.run(_scenario())


def test_run_skill_model_usage_executes_local_script_binding(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "model-usage",
        "name: model-usage\ndescription: usage\nscript: model_usage",
    )
    input_path = tmp_path / "usage.json"
    input_path.write_text(
        json.dumps(
            {
                "provider": "codex",
                "daily": [
                    {
                        "date": "2026-03-06",
                        "modelBreakdowns": [
                            {"modelName": "gpt-5-codex", "cost": 4.25},
                            {"modelName": "gpt-4.1-mini", "cost": 1.5},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {
                "name": "model-usage",
                "tool_arguments": {"provider": "codex", "mode": "all", "input": str(input_path)},
            },
            ToolContext(session_id="cli:model-usage"),
        )
        assert "Provider: codex" in out
        assert "gpt-5-codex" in out

    asyncio.run(_scenario())


def test_run_skill_session_logs_reads_jsonl_without_jq_or_rg(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "session-logs",
        "name: session-logs\ndescription: logs\nscript: session_logs",
    )
    state_path = tmp_path / "state"
    sessions_dir = state_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(state_path),
            }
        ),
        encoding="utf-8",
    )
    (sessions_dir / "cli_history.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"session_id": "cli:history", "role": "user", "content": "deploy status", "ts": "2026-03-07T00:00:00Z", "metadata": {"channel": "telegram"}}),
                json.dumps({"session_id": "cli:history", "role": "assistant", "content": "deployment healthy", "ts": "2026-03-07T00:01:00Z", "metadata": {"channel": "telegram"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run(
            {
                "name": "session-logs",
                "tool_arguments": {"config": str(config_path), "session_id": "cli:history", "role": "assistant"},
            },
            ToolContext(session_id="cli:logs"),
        )
        payload = json.loads(out)
        assert payload["status"] == "ok"
        assert payload["session_id"] == "cli:history"
        assert payload["count"] == 1
        assert payload["messages"][0]["content"] == "deployment healthy"

    asyncio.run(_scenario())
