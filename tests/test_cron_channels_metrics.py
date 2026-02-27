from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from clawlite.runtime import multiagent


def _patch_db(tmp_path):
    old_dir = multiagent.DB_DIR
    old_path = multiagent.DB_PATH
    multiagent.DB_DIR = tmp_path / ".clawlite"
    multiagent.DB_PATH = multiagent.DB_DIR / "multiagent.db"
    return old_dir, old_path


def _boot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    server = importlib.import_module("clawlite.gateway.server")
    importlib.reload(server)
    return server


def test_cron_list_add_remove(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        # lista vazia inicial
        r = client.get("/api/cron", headers=headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["jobs"] == []

        # adiciona job
        added = client.post(
            "/api/cron",
            headers=headers,
            json={
                "channel": "telegram",
                "chat_id": "123",
                "name": "teste-cron",
                "text": "ping",
                "interval_seconds": 60,
            },
        )
        assert added.status_code == 200
        job_id = added.json()["id"]
        assert job_id > 0

        # lista após adicionar
        listed = client.get("/api/cron", headers=headers)
        assert listed.status_code == 200
        jobs = listed.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["name"] == "teste-cron"

        # remove job
        removed = client.delete(f"/api/cron/{job_id}", headers=headers)
        assert removed.status_code == 200
        assert removed.json()["ok"] is True

        # lista vazia após remover
        final = client.get("/api/cron", headers=headers)
        assert final.json()["jobs"] == []

        # remove inexistente → 404
        not_found = client.delete(f"/api/cron/{job_id}", headers=headers)
        assert not_found.status_code == 404
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path


def test_channels_status(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        # sem canais configurados
        r = client.get("/api/channels/status", headers=headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # salva config com canal telegram
        from clawlite.config.settings import save_config, load_config
        cfg = load_config()
        cfg["channels"] = {
            "telegram": {"enabled": True, "token": "fake-token", "stt_enabled": True, "tts_enabled": False}
        }
        save_config(cfg)

        r2 = client.get("/api/channels/status", headers=headers)
        assert r2.status_code == 200
        channels = r2.json()["channels"]
        tg = next(c for c in channels if c["channel"] == "telegram")
        assert tg["enabled"] is True
        assert tg["configured"] is True
        assert tg["stt_enabled"] is True
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path


def test_metrics(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        r = client.get("/api/metrics", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "uptime_seconds" in data
        assert "workers" in data
        assert "tasks" in data
        assert "log_ring" in data
        assert "websocket_connections" in data
        assert data["uptime_seconds"] >= 0
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path
