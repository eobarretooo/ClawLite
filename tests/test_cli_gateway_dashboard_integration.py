from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient


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


def _boot_gateway(monkeypatch, tmp_path: Path, extra_env: dict[str, str] | None = None):
    monkeypatch.setenv("HOME", str(tmp_path))
    if extra_env:
        for key, value in extra_env.items():
            monkeypatch.setenv(key, value)

    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    server = importlib.import_module("clawlite.gateway.server")
    importlib.reload(server)
    return server, TestClient(server.app)


def _auth_headers(server) -> dict[str, str]:
    token = server._token()
    return {"Authorization": f"Bearer {token}"}


def test_auth_cli_ptbr_and_dashboard_auth(monkeypatch, tmp_path):
    status = _run_cli(tmp_path, "auth", "status")
    assert status.returncode == 0
    assert "não autenticado" in status.stdout

    logout = _run_cli(tmp_path, "auth", "logout", "openai")
    assert logout.returncode == 0
    assert "já estava desconectado" in logout.stdout

    server, client = _boot_gateway(monkeypatch, tmp_path)
    token = server._token()
    res = client.post("/api/dashboard/auth", json={"token": token})
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_battery_cli_reflects_config_and_dashboard_bootstrap(monkeypatch, tmp_path):
    set_mode = _run_cli(tmp_path, "battery", "set", "--enabled", "true", "--throttle-seconds", "9")
    assert set_mode.returncode == 0
    assert "Modo bateria atualizado." in set_mode.stdout

    show_mode = _run_cli(tmp_path, "battery", "status")
    assert show_mode.returncode == 0
    assert "modo_bateria.ativo: True" in show_mode.stdout
    assert "modo_bateria.intervalo_segundos: 9.0" in show_mode.stdout

    server, client = _boot_gateway(monkeypatch, tmp_path)
    boot = client.get("/api/dashboard/bootstrap", headers=_auth_headers(server))
    assert boot.status_code == 200
    assert boot.json()["ok"] is True


def test_cron_cli_error_ptbr_and_dashboard_status(monkeypatch, tmp_path):
    add = _run_cli(
        tmp_path,
        "cron",
        "add",
        "--channel",
        "telegram",
        "--chat-id",
        "123",
        "--thread-id",
        "suporte",
        "--label",
        "geral",
        "--name",
        "heartbeat",
        "--text",
        "ping",
        "--every-seconds",
        "0",
    )
    assert add.returncode == 1
    assert "Falha no comando 'cron': interval_seconds deve ser maior que 0" in add.stdout

    server, client = _boot_gateway(monkeypatch, tmp_path)
    status = client.get("/api/dashboard/status", headers=_auth_headers(server))
    assert status.status_code == 200
    assert status.json()["ok"] is True


def test_start_cli_invalid_gateway_port_is_actionable(tmp_path):
    cfg_dir = tmp_path / ".clawlite"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"gateway": {"host": "0.0.0.0", "port": "abc", "token": "x"}}),
        encoding="utf-8",
    )

    start = _run_cli(tmp_path, "start")
    assert start.returncode == 1
    assert "Falha ao iniciar gateway: Configuração inválida do gateway" in start.stdout
    assert "Traceback" not in start.stderr


def test_agents_cli_error_ptbr_and_dashboard_logs(monkeypatch, tmp_path):
    start = _run_cli(tmp_path, "agents", "start", "999")
    assert start.returncode == 1
    assert "Falha no comando 'agents': worker 999 não encontrado" in start.stdout

    server, client = _boot_gateway(monkeypatch, tmp_path)
    logs = client.get("/api/dashboard/logs", headers=_auth_headers(server))
    assert logs.status_code == 200
    assert logs.json()["ok"] is True


def test_skill_publish_cli_and_gateway_hub_lookup(monkeypatch, tmp_path):
    skill_dir = tmp_path / "skill-demo"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# Skill de teste\n", encoding="utf-8")

    hub_dir = tmp_path / "hub-out"
    manifest_path = tmp_path / "manifest" / "manifest.local.json"
    publish = _run_cli(
        tmp_path,
        "skill",
        "publish",
        str(skill_dir),
        "--version",
        "1.0.0",
        "--slug",
        "skill-demo",
        "--description",
        "integração",
        "--hub-dir",
        str(hub_dir),
        "--manifest-path",
        str(manifest_path),
        "--download-base-url",
        "https://example.local/packages",
    )
    assert publish.returncode == 0
    assert "skill publicada: skill-demo@1.0.0" in publish.stdout
    assert f"manifesto: {manifest_path}" in publish.stdout

    server, client = _boot_gateway(monkeypatch, tmp_path, {"CLAWLITE_HUB_MANIFEST": str(manifest_path)})
    hub_skill = client.get("/api/hub/skills/skill-demo")
    assert hub_skill.status_code == 200
    assert hub_skill.json()["skill"]["version"] == "1.0.0"

    boot = client.get("/api/dashboard/bootstrap", headers=_auth_headers(server))
    assert boot.status_code == 200


def test_pairing_cli_list_empty(tmp_path):
    out = _run_cli(tmp_path, "pairing", "list")
    assert out.returncode == 0
    assert "Nenhuma solicitação de pairing pendente" in out.stdout


def test_backup_cli_create_and_list(tmp_path):
    seed = _run_cli(tmp_path, "battery", "set", "--enabled", "false")
    assert seed.returncode == 0

    created = _run_cli(tmp_path, "backup", "create", "--label", "ci")
    assert created.returncode == 0
    assert "Backup criado" in created.stdout

    listed = _run_cli(tmp_path, "backup", "list")
    assert listed.returncode == 0
    assert "clawlite_backup_" in listed.stdout
