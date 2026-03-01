from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(tmp_home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    return subprocess.run(
        [sys.executable, "-m", "clawlite.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def test_providers_use_and_current(tmp_path: Path) -> None:
    use = _run_cli(tmp_path, "providers", "use", "gemini", "--model", "gemini-2.5-flash")
    assert use.returncode == 0
    assert "Provider ativo atualizado" in use.stdout
    assert "gemini/gemini-2.5-flash" in use.stdout

    current = _run_cli(tmp_path, "providers", "current")
    assert current.returncode == 0
    assert "provider: gemini" in current.stdout
    assert "model: gemini/gemini-2.5-flash" in current.stdout


def test_channels_and_skills_list_commands(tmp_path: Path) -> None:
    channels = _run_cli(tmp_path, "channels", "list")
    assert channels.returncode == 0
    assert "- telegram:" in channels.stdout

    skills = _run_cli(tmp_path, "skills", "list", "--all")
    assert skills.returncode == 0
    assert "- " in skills.stdout


def test_agent_one_shot_local_path(tmp_path: Path) -> None:
    out = _run_cli(tmp_path, "agent", "-m", "quem voce e?")
    assert out.returncode == 0
    assert out.stdout.strip()
    assert "Traceback" not in out.stderr
