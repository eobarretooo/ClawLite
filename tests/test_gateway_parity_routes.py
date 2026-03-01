from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient


def _boot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    server = importlib.import_module("clawlite.gateway.server")
    importlib.reload(server)
    return settings, server


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def test_sessions_routes_parity(monkeypatch, tmp_path):
    settings, server = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)
    token = server._token()
    headers = {"Authorization": f"Bearer {token}"}

    dashboard = Path(settings.CONFIG_DIR) / "dashboard"
    sessions_path = dashboard / "sessions.jsonl"
    telemetry_path = dashboard / "telemetry.jsonl"
    _write_jsonl(
        sessions_path,
        [
            {"ts": "2026-03-01T00:00:00Z", "session_id": "s1", "role": "user", "text": "oi"},
            {"ts": "2026-03-01T00:00:01Z", "session_id": "s1", "role": "assistant", "text": "ola"},
            {"ts": "2026-03-01T00:00:02Z", "session_id": "s1", "role": "user", "text": "novo"},
            {"ts": "2026-03-01T00:00:03Z", "session_id": "s2", "role": "user", "text": "x"},
            {"ts": "2026-03-01T00:00:04Z", "session_id": "s2", "role": "assistant", "text": "y"},
        ],
    )
    _write_jsonl(
        telemetry_path,
        [
            {"ts": "2026-03-01T00:00:01Z", "session_id": "s1", "tokens": 10, "cost_usd": 0.01},
            {"ts": "2026-03-01T00:00:04Z", "session_id": "s2", "tokens": 8, "cost_usd": 0.008},
        ],
    )

    listed = client.get("/api/sessions", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["ok"] is True
    assert {row["session_id"] for row in listed.json()["sessions"]} == {"s1", "s2"}

    preview = client.get("/api/sessions/s1/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["count"] == 3

    patched = client.patch("/api/sessions/s1", headers=headers, json={"rename_to": "renamed"})
    assert patched.status_code == 200
    assert patched.json()["updated"] == 3
    assert patched.json()["telemetry_updated"] == 1

    compact = client.post("/api/sessions/compact", headers=headers, json={"max_messages": 1})
    assert compact.status_code == 200
    assert compact.json()["ok"] is True
    assert compact.json()["removed"] >= 1

    reset = client.post("/api/sessions/s2/reset", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["ok"] is True

    deleted = client.delete("/api/sessions/renamed", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["messages_removed"] >= 1


def test_talk_models_and_update_alias(monkeypatch, tmp_path):
    _settings, server = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)
    token = server._token()
    headers = {"Authorization": f"Bearer {token}"}

    talk_cfg = client.get("/api/talk/config", headers=headers)
    assert talk_cfg.status_code == 200
    assert talk_cfg.json()["ok"] is True
    assert "talk" in talk_cfg.json()

    talk_mode = client.put(
        "/api/talk/mode",
        headers=headers,
        json={"enabled": True, "mode": "voice", "phase": "listening"},
    )
    assert talk_mode.status_code == 200
    assert talk_mode.json()["ok"] is True
    assert talk_mode.json()["mode"] == "voice"

    models = client.get("/api/models/list", headers=headers)
    assert models.status_code == 200
    assert models.json()["ok"] is True
    assert isinstance(models.json()["models"], list)
    assert len(models.json()["models"]) >= 1

    monkeypatch.setattr(server, "update_skills", lambda **kwargs: {"updated": [], "skipped": [], "blocked": [], "missing": []})
    update_run = client.post("/api/update/run", headers=headers, json={"dry_run": True, "slugs": ["abc"]})
    assert update_run.status_code == 200
    assert update_run.json()["ok"] is True
    assert update_run.json()["dry_run"] is True

