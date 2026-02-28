from __future__ import annotations

import importlib
from pathlib import Path


def _boot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    daemon = importlib.import_module("clawlite.runtime.daemon")
    importlib.reload(daemon)
    backup = importlib.import_module("clawlite.runtime.backup")
    importlib.reload(backup)
    return settings, daemon, backup


def test_install_daemon_writes_unit_and_calls_systemctl(monkeypatch, tmp_path):
    _settings, daemon, _backup = _boot(monkeypatch, tmp_path)

    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(daemon.shutil, "which", lambda name: "/bin/systemctl" if name == "systemctl" else "")
    monkeypatch.setattr(
        daemon.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(list(cmd)) or _Proc(),
    )

    row = daemon.install_systemd_user_service(
        host="127.0.0.1",
        port=8787,
        service_name="clawlite-test",
        enable_now=True,
        start_now=True,
    )

    assert row["ok"] is True
    unit = Path(row["unit_path"])
    assert unit.exists()
    text = unit.read_text(encoding="utf-8")
    assert "ExecStart=" in text
    assert "--port 8787" in text
    assert calls[0][:3] == ["systemctl", "--user", "daemon-reload"]


def test_backup_create_list_restore(monkeypatch, tmp_path):
    settings, _daemon, backup = _boot(monkeypatch, tmp_path)
    cfg_dir = settings.CONFIG_DIR
    cfg_dir.mkdir(parents=True, exist_ok=True)

    (cfg_dir / "config.json").write_text('{"gateway":{"port":8787}}', encoding="utf-8")
    (cfg_dir / "learning.db").write_bytes(b"sqlite-bytes")
    workspace = cfg_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    note = workspace / "NOTE.md"
    note.write_text("v1", encoding="utf-8")

    created = backup.create_backup(label="test", keep_last=3)
    assert created["ok"] is True
    assert Path(created["archive"]).exists()

    listed = backup.list_backups()
    assert listed
    assert listed[0]["name"].endswith(".tar.gz")

    # sobrescreve conteúdo e restaura
    note.write_text("corrompido", encoding="utf-8")
    restored = backup.restore_backup(created["archive"])
    assert restored["ok"] is True
    assert note.read_text(encoding="utf-8") == "v1"
