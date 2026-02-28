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


def test_extract_version_from_ref_accepts_beta_tag():
    assert self_update._extract_version_from_ref("v0.4.2-beta.1") == "0.4.2-beta.1"


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
        lambda: {
            "current_version": "0.4.1",
            "latest_version_dev": "0.4.3",
            "checked_at_dev": now,
            "source_dev": "cache",
        },
    )
    monkeypatch.setattr(self_update, "_check_interval_seconds", lambda: 3600)
    monkeypatch.setattr(
        self_update,
        "_fetch_remote_target",
        lambda channel, timeout=2.5: self_update.UpdateTarget(
            version="0.4.9",
            source="main",
            ref="main",
        ),
    )

    status = self_update.check_for_updates(force_remote=False, channel="dev")
    assert status.source == "cache"
    assert status.available is True
    assert status.latest_version == "0.4.3"
    assert status.channel == "dev"


def test_check_for_updates_remote(monkeypatch):
    saved: dict[str, object] = {}
    monkeypatch.setattr(self_update, "_current_version", lambda: "0.4.1")
    monkeypatch.setattr(self_update, "_load_cache", lambda: {})
    monkeypatch.setattr(
        self_update,
        "_fetch_remote_target",
        lambda channel, timeout=2.5: self_update.UpdateTarget(
            version="0.4.5",
            source="main",
            ref="main",
        ),
    )
    monkeypatch.setattr(self_update, "_save_cache", lambda payload: saved.update(payload))

    status = self_update.check_for_updates(force_remote=True, channel="dev")
    assert status.source == "main"
    assert status.available is True
    assert status.latest_version == "0.4.5"
    assert saved.get("latest_version_dev") == "0.4.5"
    assert saved.get("target_ref_dev") == "main"


def test_format_update_notice():
    status = self_update.UpdateStatus(
        current_version="0.4.1",
        latest_version="0.4.5",
        available=True,
        source="remote",
        channel="beta",
        target_ref="v0.4.5-beta.1",
    )
    notice = self_update.format_update_notice(status)
    assert "0.4.1" in notice
    assert "0.4.5" in notice
    assert "beta" in notice
    assert "clawlite update" in notice


def test_fetch_remote_target_beta_prefers_stable_when_newer(monkeypatch):
    monkeypatch.setattr(
        self_update,
        "_fetch_latest_beta_release_target",
        lambda timeout=2.5: self_update.UpdateTarget(
            version="0.4.1-beta.1",
            source="release-beta",
            ref="v0.4.1-beta.1",
        ),
    )
    monkeypatch.setattr(
        self_update,
        "_fetch_latest_stable_release_target",
        lambda timeout=2.5: self_update.UpdateTarget(
            version="0.4.2",
            source="release-stable",
            ref="v0.4.2",
        ),
    )

    target = self_update._fetch_remote_target("beta")
    assert target.version == "0.4.2"
    assert target.ref == "v0.4.2"
    assert target.source == "release-stable-fallback-beta"


def test_run_self_update_fallback_pip_stable_tag(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(self_update, "_find_local_repo_root", lambda: None)
    monkeypatch.setattr(
        self_update,
        "_fetch_remote_target",
        lambda channel, timeout=2.5: self_update.UpdateTarget(
            version="0.5.0",
            source="release-stable",
            ref="v0.5.0",
        ),
    )

    def _fake_run(cmd: list[str]):
        calls.append(cmd)
        return True, ""

    monkeypatch.setattr(self_update, "_run", _fake_run)

    ok, msg = self_update.run_self_update(channel="stable")
    assert ok is True
    assert calls
    joined = " ".join(calls[0])
    assert "pip install --upgrade" in joined
    assert "git+https://github.com/eobarretooo/ClawLite.git@v0.5.0" in joined
    assert "stable" in msg
    assert "0.5.0" in msg


def test_run_self_update_local_repo(monkeypatch):
    calls: list[list[str]] = []
    repo = Path("/tmp/clawlite-repo")

    monkeypatch.setattr(self_update, "_find_local_repo_root", lambda: repo)
    monkeypatch.setattr(self_update, "_repo_is_clean", lambda _: True)
    monkeypatch.setattr(
        self_update,
        "_fetch_remote_target",
        lambda channel, timeout=2.5: self_update.UpdateTarget(
            version="0.5.0",
            source="main",
            ref="main",
        ),
    )

    def _fake_run(cmd: list[str]):
        calls.append(cmd)
        return True, ""

    monkeypatch.setattr(self_update, "_run", _fake_run)

    ok, msg = self_update.run_self_update(channel="dev")
    assert ok is True
    assert len(calls) == 2
    assert calls[0][:4] == ["git", "-C", str(repo), "pull"]
    assert "dev" in msg
    assert "0.5.0" in msg
