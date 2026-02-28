from __future__ import annotations

import clawlite.skills.openclaw_compat as compat
from clawlite.skills import registry


def test_openclaw_compat_delegate_gh_issues(monkeypatch):
    import clawlite.skills.github as github

    monkeypatch.setattr(github, "run", lambda command="": f"github:{command}")
    out = compat.run_gh_issues("issue list")
    assert out == "github:issue list"


def test_openclaw_compat_delegate_openai_whisper(monkeypatch):
    import clawlite.skills.whisper as whisper

    monkeypatch.setattr(whisper, "run", lambda command="": f"whisper:{command}")
    out = compat.run_openai_whisper("transcribe /tmp/a.wav")
    assert out == "whisper:transcribe /tmp/a.wav"


def test_openclaw_compat_unsupported_returns_guidance():
    out = compat.run_1password("list vaults")
    assert "openclaw-compat:1password" in out
    assert "Alternativas" in out


def test_registry_includes_openclaw_aliases():
    assert "gh-issues" in registry.SKILLS
    assert "openai-whisper" in registry.SKILLS
    assert "xurl" in registry.SKILLS
    assert "1password" in registry.SKILLS
    assert "Compat OpenClaw" in registry.describe_skill("gh-issues")
