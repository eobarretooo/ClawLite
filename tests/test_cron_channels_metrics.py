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
        assert "outbound" in tg
        assert tg["outbound"]["sent_ok"] == 0
        assert tg["outbound"]["retry_count"] == 0
        assert tg["outbound"]["timeout_count"] == 0
        assert tg["outbound"]["fallback_count"] == 0
        assert tg["outbound"]["send_fail_count"] == 0
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path


def test_channels_status_token_optional_channels(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        from clawlite.config.settings import load_config, save_config

        cfg = load_config()
        cfg["channels"] = {
            "googlechat": {
                "enabled": True,
                "serviceAccountFile": "/tmp/service-account.json",
            },
            "irc": {
                "enabled": True,
                "host": "irc.libera.chat",
                "nick": "clawlite-bot",
            },
            "signal": {
                "enabled": True,
                "account": "+15551234567",
            },
            "imessage": {
                "enabled": True,
                "cliPath": "imsg",
            },
        }
        save_config(cfg)

        status = client.get("/api/channels/status", headers=headers)
        assert status.status_code == 200
        rows = {row["channel"]: row for row in status.json()["channels"]}

        assert rows["googlechat"]["configured"] is True
        assert rows["irc"]["configured"] is True
        assert rows["signal"]["configured"] is True
        assert rows["imessage"]["configured"] is True
        assert rows["googlechat"]["outbound"]["sent_ok"] == 0
        assert rows["irc"]["outbound"]["retry_count"] == 0
        assert rows["signal"]["outbound"]["timeout_count"] == 0
        assert rows["imessage"]["outbound"]["fallback_count"] == 0
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path


def test_channels_status_exposes_live_outbound_metrics(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        from clawlite.config.settings import load_config, save_config

        cfg = load_config()
        cfg["channels"] = {
            "irc": {"enabled": True, "host": "irc.libera.chat", "nick": "clawlite-bot"},
        }
        save_config(cfg)
        monkeypatch.setattr(
            server.channels.manager,
            "outbound_metrics",
            lambda channel_name=None: {
                "irc": {
                    "sent_ok": 7,
                    "retry_count": 3,
                    "timeout_count": 1,
                    "fallback_count": 2,
                    "send_fail_count": 2,
                    "dedupe_hits": 4,
                    "instances_reporting": 1,
                }
            },
        )

        status = client.get("/api/channels/status", headers=headers)
        assert status.status_code == 200
        row = next(c for c in status.json()["channels"] if c["channel"] == "irc")
        assert row["outbound"]["sent_ok"] == 7
        assert row["outbound"]["retry_count"] == 3
        assert row["outbound"]["timeout_count"] == 1
        assert row["outbound"]["fallback_count"] == 2
        assert row["outbound"]["send_fail_count"] == 2
        assert row["outbound"]["instances_reporting"] == 1
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path


def test_config_apply_restart_and_debug(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        dry = client.post(
            "/api/dashboard/config/apply",
            headers=headers,
            json={
                "dry_run": True,
                "model": "openai/gpt-4o-mini",
                "channels": {"telegram": {"enabled": True, "token": "x"}},
            },
        )
        assert dry.status_code == 200
        assert dry.json()["dry_run"] is True

        apply_real = client.post(
            "/api/dashboard/config/apply",
            headers=headers,
            json={
                "dry_run": False,
                "model": "openai/gpt-4o-mini",
                "channels": {"telegram": {"enabled": True, "token": "abc", "account": "acc-1"}},
            },
        )
        assert apply_real.status_code == 200
        assert apply_real.json()["settings"]["model"] == "openai/gpt-4o-mini"

        restart = client.post("/api/dashboard/config/restart", headers=headers, json={"mode": "safe"})
        assert restart.status_code == 200
        assert restart.json()["performed"] is False

        debug = client.get("/api/dashboard/debug", headers=headers)
        assert debug.status_code == 200
        info = debug.json()["debug"]
        assert "version" in info
        assert "python" in info
        assert "config_dir" in info
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path


def test_channels_config_and_update_endpoint(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        saved = client.put(
            "/api/channels/config",
            headers=headers,
            json={
                "channels": {
                    "telegram": {
                        "enabled": True,
                        "token": "tok",
                        "account": "acc",
                        "stt_enabled": True,
                        "tts_enabled": False,
                    },
                    "slack": {
                        "enabled": True,
                        "token": "xoxb-main",
                        "app_token": "xapp-main",
                        "workspace": "main",
                        "allowFrom": ["C-main"],
                        "accounts": [{"account": "dev", "token": "xoxb-dev", "app_token": "xapp-dev"}],
                    },
                    "googlechat": {
                        "enabled": True,
                        "serviceAccountFile": "/tmp/service-account.json",
                        "botUser": "users/123",
                        "outboundWebhookUrl": "https://example.test/googlechat",
                        "sendTimeoutSec": 9.0,
                        "requireMention": True,
                        "dm": {"policy": "pairing", "allowFrom": ["users/999"]},
                    },
                    "irc": {
                        "enabled": True,
                        "host": "irc.libera.chat",
                        "port": 6697,
                        "tls": True,
                        "nick": "clawlite-bot",
                        "channels": ["#clawlite"],
                        "sendTimeoutSec": 11.0,
                        "requireMention": True,
                    },
                    "signal": {
                        "enabled": True,
                        "account": "+15551234567",
                        "cliPath": "signal-cli",
                        "sendTimeoutSec": 17.0,
                    },
                    "imessage": {
                        "enabled": True,
                        "cliPath": "imsg",
                        "service": "auto",
                        "sendTimeoutSec": 19.0,
                    },
                }
            },
        )
        assert saved.status_code == 200
        assert saved.json()["channels"]["telegram"]["enabled"] is True
        assert saved.json()["channels"]["slack"]["app_token"] == "xapp-main"
        assert saved.json()["channels"]["slack"]["accounts"][0]["account"] == "dev"
        assert saved.json()["channels"]["slack"]["accounts"][0]["app_token"] == "xapp-dev"
        assert saved.json()["channels"]["googlechat"]["serviceAccountFile"] == "/tmp/service-account.json"
        assert saved.json()["channels"]["googlechat"]["outboundWebhookUrl"] == "https://example.test/googlechat"
        assert saved.json()["channels"]["googlechat"]["sendTimeoutSec"] == 9.0
        assert saved.json()["channels"]["irc"]["host"] == "irc.libera.chat"
        assert saved.json()["channels"]["irc"]["sendTimeoutSec"] == 11.0
        assert saved.json()["channels"]["signal"]["account"] == "+15551234567"
        assert saved.json()["channels"]["signal"]["sendTimeoutSec"] == 17.0
        assert saved.json()["channels"]["imessage"]["cliPath"] == "imsg"
        assert saved.json()["channels"]["imessage"]["sendTimeoutSec"] == 19.0

        status = client.get("/api/channels/status", headers=headers)
        tg = next(c for c in status.json()["channels"] if c["channel"] == "telegram")
        assert tg["configured"] is True
        sl = next(c for c in status.json()["channels"] if c["channel"] == "slack")
        assert sl["configured"] is True
        assert "accounts_configured" in sl
        assert "outbound" in sl
        assert sl["outbound"]["sent_ok"] == 0
        assert next(c for c in status.json()["channels"] if c["channel"] == "googlechat")["configured"] is True
        assert next(c for c in status.json()["channels"] if c["channel"] == "irc")["configured"] is True
        assert next(c for c in status.json()["channels"] if c["channel"] == "signal")["configured"] is True
        assert next(c for c in status.json()["channels"] if c["channel"] == "imessage")["configured"] is True

        # evita rede no teste do update
        monkeypatch.setattr(server, "update_skills", lambda **kwargs: {"updated": [], "skipped": [], "blocked": [], "missing": []})
        up = client.post("/api/dashboard/update", headers=headers, json={"dry_run": True, "slugs": ["abc"]})
        assert up.status_code == 200
        assert up.json()["ok"] is True
        assert up.json()["dry_run"] is True
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path


def test_channels_instances_and_reconnect_endpoint(monkeypatch, tmp_path):
    old_dir, old_path = _patch_db(tmp_path)
    try:
        server = _boot(monkeypatch, tmp_path)
        client = TestClient(server.app)
        token = server._token()
        headers = {"Authorization": f"Bearer {token}"}

        monkeypatch.setattr(
            server.channels.manager,
            "describe_instances",
            lambda channel_name=None: [
                {"instance_key": "telegram", "channel": "telegram", "account": "", "running": True}
            ],
        )
        async def _fake_reconnect(channel):
            return {
                "channel": channel,
                "enabled": True,
                "stopped": [channel],
                "started": [channel],
            }

        monkeypatch.setattr(server.channels.manager, "reconnect_channel", _fake_reconnect)

        instances = client.get("/api/channels/instances", headers=headers)
        assert instances.status_code == 200
        assert instances.json()["ok"] is True
        assert instances.json()["instances"][0]["instance_key"] == "telegram"

        reconnect = client.post("/api/channels/reconnect", headers=headers, json={"channel": "telegram"})
        assert reconnect.status_code == 200
        assert reconnect.json()["ok"] is True
        assert reconnect.json()["channel"] == "telegram"
        assert reconnect.json()["started"] == ["telegram"]
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
        monkeypatch.setattr(
            server.channels.manager,
            "outbound_metrics",
            lambda channel_name=None: {
                "irc": {
                    "sent_ok": 7,
                    "retry_count": 3,
                    "timeout_count": 1,
                    "fallback_count": 2,
                    "send_fail_count": 2,
                    "dedupe_hits": 4,
                    "instances_reporting": 1,
                }
            },
        )

        r = client.get("/api/metrics", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "uptime_seconds" in data
        assert "workers" in data
        assert "tasks" in data
        assert "log_ring" in data
        assert "websocket_connections" in data
        assert "channels_outbound" in data
        assert data["channels_outbound"]["channels_reporting"] == 1
        assert data["channels_outbound"]["totals"]["sent_ok"] == 7
        assert data["channels_outbound"]["totals"]["retry_count"] == 3
        assert data["channels_outbound"]["totals"]["timeout_count"] == 1
        assert data["channels_outbound"]["totals"]["fallback_count"] == 2
        assert data["channels_outbound"]["totals"]["send_fail_count"] == 2
        assert data["uptime_seconds"] >= 0
    finally:
        multiagent.DB_DIR = old_dir
        multiagent.DB_PATH = old_path
