from __future__ import annotations

import importlib
from pathlib import Path


def _reload(monkeypatch, tmp_home: Path):
    monkeypatch.setenv("HOME", str(tmp_home))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    discovery = importlib.import_module("clawlite.skills.discovery")
    importlib.reload(discovery)
    mcp = importlib.import_module("clawlite.mcp")
    importlib.reload(mcp)
    return discovery, mcp


def _write_skill(
    root: Path,
    slug: str,
    frontmatter: str,
    body: str = "# Skill\n",
) -> Path:
    skill_dir = root / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(frontmatter + "\n" + body, encoding="utf-8")
    return skill_dir


def test_discovery_creates_runtime_skill_dirs_and_includes_builtin(monkeypatch, tmp_path: Path) -> None:
    discovery, _ = _reload(monkeypatch, tmp_path)
    ws_skills = tmp_path / ".clawlite" / "workspace" / "skills"
    mp_skills = tmp_path / ".clawlite" / "marketplace" / "skills"

    assert not ws_skills.exists()
    assert not mp_skills.exists()

    rows = discovery.discover_skill_docs()

    assert ws_skills.exists()
    assert mp_skills.exists()
    assert any(row.source == "builtin" for row in rows)


def test_mcp_autoloads_and_executes_dynamic_command_skill(monkeypatch, tmp_path: Path) -> None:
    _, mcp = _reload(monkeypatch, tmp_path)
    ws_root = tmp_path / ".clawlite" / "workspace" / "skills"
    _write_skill(
        ws_root,
        "git-operations",
        """---
name: git-operations
description: Skill dinâmica para operação git
always: true
command: printf "git-op:%s" {command}
---""",
    )

    tools = mcp.mcp_tools_from_skills()
    assert any(tool["name"] == "skill.git-operations" for tool in tools)

    out = mcp.dispatch_skill_tool("skill.git-operations", {"command": "status"})
    text = out["content"][0]["text"]
    assert "git-op:status" in text


def test_mcp_autoloads_and_executes_dynamic_script_skill(monkeypatch, tmp_path: Path) -> None:
    _, mcp = _reload(monkeypatch, tmp_path)
    ws_root = tmp_path / ".clawlite" / "workspace" / "skills"
    skill_dir = _write_skill(
        ws_root,
        "code-analysis",
        """---
name: code-analysis
description: Skill dinâmica por script
always: false
script: run.py
---""",
    )
    (skill_dir / "run.py").write_text(
        "import sys\n"
        "query = sys.argv[1] if len(sys.argv) > 1 else 'none'\n"
        "print(f'analysis:{query}')\n",
        encoding="utf-8",
    )

    tools = mcp.mcp_tools_from_skills()
    assert any(tool["name"] == "skill.code-analysis" for tool in tools)

    out = mcp.dispatch_skill_tool("skill.code-analysis", {"command": "README.md"})
    text = out["content"][0]["text"]
    assert "analysis:README.md" in text
