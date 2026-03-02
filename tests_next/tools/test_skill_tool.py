from __future__ import annotations

import asyncio
from pathlib import Path

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
        return f"query:{arguments.get('query', '')}:{ctx.session_id}"


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
        out = await tool.run({"name": "web", "query": "nanobot"}, ToolContext(session_id="s3"))
        assert out == "query:nanobot:s3"

    asyncio.run(_scenario())


def test_run_skill_returns_not_executable_when_no_binding(tmp_path: Path) -> None:
    _write_skill(tmp_path, "doc-only", "name: doc-only\ndescription: doc only")

    async def _scenario() -> None:
        reg = ToolRegistry()
        tool = SkillTool(loader=SkillsLoader(builtin_root=tmp_path), registry=reg)
        out = await tool.run({"name": "doc-only"}, ToolContext(session_id="s4"))
        assert out == "skill_not_executable:doc-only"

    asyncio.run(_scenario())
