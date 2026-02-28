from __future__ import annotations

from pathlib import Path

from clawlite.runtime import self_update


def test_extract_version_from_pyproject():
    text = """
[project]
name = "clawlite"
version = "0.4.2"
"""
    assert self_update._extract_version_from_pyproject(text) == "0.4.2"


def test_version_comparison():
    assert self_update._is_newer_version("0.4.2", "0.4.1") is True
    assert self_update._is_newer_version("0.4.1", "0.4.1") is False
    assert self_update._is_newer_version("0.4.0", "0.4.1") is False


def test_check_for_updates_uses_fresh_cache(monkeypatch):
    now = self_update._now_ts()
    monkeypatch.setattr(self_update, "_current_version", lambda: "0.4.1")
    monkeypatch.setattr(
        self_update,
        "_load_cache",
        lambda: {"current_version": "0.4.1", "latest_version": "0.4.3", "checked_at": now},
    )
    monkeypatch.setattr(self_update, "_check_interval_seconds", lambda: 3600)
    monkeypatch.setattr(self_update, "_fetch_remote_version", lambda timeout=2.5: "0.4.9")

    status = self_update.check_for_updates(force_remote=False)
    assert status.source == "cache"
    assert status.available is True
    assert status.latest_version == "0.4.3"


def test_check_for_updates_remote(monkeypatch):
    saved: dict[str, object] = {}
    monkeypatch.setattr(self_update, "_current_version", lambda: "0.4.1")
    monkeypatch.setattr(self_update, "_load_cache", lambda: {})
    monkeypatch.setattr(self_update, "_fetch_remote_version", lambda timeout=2.5: "0.4.5")
    monkeypatch.setattr(self_update, "_save_cache", lambda payload: saved.update(payload))

    status = self_update.check_for_updates(force_remote=True)
    assert status.source == "remote"
    assert status.available is True
    assert status.latest_version == "0.4.5"
    assert saved.get("latest_version") == "0.4.5"


def test_format_update_notice():
    status = self_update.UpdateStatus(
        current_version="0.4.1",
        latest_version="0.4.5",
        available=True,
        source="remote",
    )
    notice = self_update.format_update_notice(status)
    assert "0.4.1" in notice
    assert "0.4.5" in notice
    assert "clawlite update" in notice


def test_run_self_update_fallback_pip(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(self_update, "_find_local_repo_root", lambda: None)
    monkeypatch.setattr(self_update, "_fetch_remote_version", lambda timeout=2.5: "0.5.0")

    def _fake_run(cmd: list[str]):
        calls.append(cmd)
        return True, ""

    monkeypatch.setattr(self_update, "_run", _fake_run)

    ok, msg = self_update.run_self_update()
    assert ok is True
    assert calls
    joined = " ".join(calls[0])
    assert "pip install --upgrade" in joined
    assert "git+https://github.com/eobarretooo/ClawLite.git" in joined
    assert "0.5.0" in msg


def test_run_self_update_local_repo(monkeypatch):
    calls: list[list[str]] = []
    repo = Path("/tmp/clawlite-repo")

    monkeypatch.setattr(self_update, "_find_local_repo_root", lambda: repo)
    monkeypatch.setattr(self_update, "_repo_is_clean", lambda _: True)
    monkeypatch.setattr(self_update, "_fetch_remote_version", lambda timeout=2.5: "0.5.0")

    def _fake_run(cmd: list[str]):
        calls.append(cmd)
        return True, ""

    monkeypatch.setattr(self_update, "_run", _fake_run)

    ok, msg = self_update.run_self_update()
    assert ok is True
    assert len(calls) == 2
    assert calls[0][:4] == ["git", "-C", str(repo), "pull"]
    assert "0.5.0" in msg

