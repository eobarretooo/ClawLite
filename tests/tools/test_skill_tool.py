from __future__ import annotations

import asyncio
from pathlib import Path

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


class FakeMemory:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    def integration_policy(self, kind: str, *, session_id: str):
        self.calls.append((kind, session_id))
        return self.verdict


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
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        reg.register(tool)
        out = await tool.run(
            {"name": "echo-skill", "input": "hello world"},
            ToolContext(session_id="s1"),
        )
        assert "exit=0" in out
        assert "hello world" in out

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


def test_run_skill_blocks_dangerous_command_without_exec_tool(tmp_path: Path, monkeypatch) -> None:
    _write_skill(
        tmp_path,
        "dangerous",
        "name: dangerous\ndescription: dangerous\ncommand: rm",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)

        async def _should_not_run(argv: list[str], *, timeout: float) -> str:  # pragma: no cover
            raise AssertionError("command spawn should be blocked before execution")

        monkeypatch.setattr(tool, "_run_command", _should_not_run)
        out = await tool.run(
            {"name": "dangerous", "args": ["-rf", "/"]},
            ToolContext(session_id="s7", channel="cli", user_id="u1"),
        )
        assert out == "skill_blocked:dangerous:blocked_by_policy:deny_pattern"

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


def test_run_skill_allows_execution_when_memory_policy_allows(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "echo-skill",
        "name: echo-skill\ndescription: echo\ncommand: echo",
    )

    async def _scenario() -> None:
        reg = ToolRegistry()
        memory = FakeMemory({"allowed": True})
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg, memory=memory)
        out = await tool.run(
            {"name": "echo-skill", "input": "hello"},
            ToolContext(session_id="s8"),
        )
        assert "exit=0" in out
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
