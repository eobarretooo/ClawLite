from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


class _FakeGoogleChatChannel:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def process_webhook_payload(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {"text": "ok"}


class _FakeIrcChannel:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def process_webhook_payload(self, payload: dict) -> None:
        self.payloads.append(payload)


class _FakeSignalChannel:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def process_webhook_payload(self, payload: dict) -> None:
        self.payloads.append(payload)


class _FakeIMessageChannel:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def process_webhook_payload(self, payload: dict) -> None:
        self.payloads.append(payload)


class _FakeTelegramChannel:
    def __init__(self, webhook_mode: bool = True) -> None:
        self.payloads: list[dict] = []
        self._webhook_mode = webhook_mode

    def is_webhook_mode(self) -> bool:
        return self._webhook_mode

    async def process_webhook_payload(self, payload: dict) -> None:
        self.payloads.append(payload)


def _boot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    server = importlib.import_module("clawlite.gateway.server")
    importlib.reload(server)
    webhooks = importlib.import_module("clawlite.gateway.routes.webhooks")
    return server, webhooks


def test_googlechat_webhook_requires_token(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeGoogleChatChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_googlechat_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"googlechat": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post(
        "/api/webhooks/googlechat",
        json={
            "type": "MESSAGE",
            "message": {
                "text": "oi",
                "sender": {"name": "users/100"},
                "space": {"name": "spaces/200"},
            },
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "unauthorized_webhook"


def test_googlechat_webhook_validates_payload(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeGoogleChatChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_googlechat_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"googlechat": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post(
        "/api/webhooks/googlechat",
        headers={"x-clawlite-webhook-token": "secret"},
        json={"type": "MESSAGE", "message": {"text": "sem sender e space"}},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_payload"


def test_googlechat_webhook_sanitizes_and_rate_limits(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeGoogleChatChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_googlechat_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"googlechat": {"webhook_token": "secret", "rate_limit_per_min": 1}}},
    )

    payload = {
        "type": "MESSAGE",
        "message": {
            "text": "Oi\x00\x01 Mundo",
            "sender": {"name": "users/100"},
            "space": {"name": "spaces/200"},
        },
    }
    headers = {"x-clawlite-webhook-token": "secret"}

    first = client.post("/api/webhooks/googlechat", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["text"] == "ok"
    assert len(fake.payloads) == 1
    assert fake.payloads[0]["message"]["text"] == "Oi Mundo"

    second = client.post("/api/webhooks/googlechat", headers=headers, json=payload)
    assert second.status_code == 429
    assert second.json()["ok"] is False
    assert second.json()["error"]["code"] == "rate_limited"


def test_irc_webhook_requires_token(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeIrcChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_irc_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"irc": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post("/api/webhooks/irc", json={"text": "oi", "sender": "alice", "channel": "#dev"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized_webhook"


def test_irc_webhook_validates_payload(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeIrcChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_irc_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"irc": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post(
        "/api/webhooks/irc",
        headers={"x-clawlite-webhook-token": "secret"},
        json={"text": "oi", "sender": "alice", "channel": "canal-sem-tralha"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_payload"


def test_irc_webhook_sanitizes_and_rate_limits(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeIrcChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_irc_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"irc": {"webhook_token": "secret", "rate_limit_per_min": 1}}},
    )

    payload = {"text": "oi\x00\x01 time", "sender": "alice", "channel": "#dev"}
    headers = {"x-clawlite-webhook-token": "secret"}
    first = client.post("/api/webhooks/irc", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert len(fake.payloads) == 1
    assert fake.payloads[0]["text"] == "oi time"

    second = client.post("/api/webhooks/irc", headers=headers, json=payload)
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


def test_signal_webhook_requires_token(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeSignalChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_signal_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"signal": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post("/api/webhooks/signal", json={"text": "oi", "source": "+1555"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized_webhook"


def test_signal_webhook_validates_payload(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeSignalChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_signal_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"signal": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post(
        "/api/webhooks/signal",
        headers={"x-clawlite-webhook-token": "secret"},
        json={"source": "+1555"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_payload"


def test_signal_webhook_sanitizes_and_rate_limits(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeSignalChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_signal_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"signal": {"webhook_token": "secret", "rate_limit_per_min": 1}}},
    )

    payload = {"text": "oi\x00\x01 signal", "source": "+15551234567"}
    headers = {"x-clawlite-webhook-token": "secret"}
    first = client.post("/api/webhooks/signal", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert len(fake.payloads) == 1
    assert fake.payloads[0]["text"] == "oi signal"

    second = client.post("/api/webhooks/signal", headers=headers, json=payload)
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


def test_imessage_webhook_requires_token(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeIMessageChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_imessage_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"imessage": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post("/api/webhooks/imessage", json={"text": "oi", "from": "user@icloud.com"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized_webhook"


def test_imessage_webhook_validates_payload(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeIMessageChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_imessage_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"imessage": {"webhook_token": "secret", "rate_limit_per_min": 20}}},
    )

    resp = client.post(
        "/api/webhooks/imessage",
        headers={"x-clawlite-webhook-token": "secret"},
        json={"from": "user@icloud.com"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_payload"


def test_imessage_webhook_sanitizes_and_rate_limits(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeIMessageChannel()
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_imessage_channel", lambda: fake)
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"imessage": {"webhook_token": "secret", "rate_limit_per_min": 1}}},
    )

    payload = {"text": "oi\x00\x01 ios", "from": "user@icloud.com", "chat_id": "chat123"}
    headers = {"x-clawlite-webhook-token": "secret"}
    first = client.post("/api/webhooks/imessage", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert len(fake.payloads) == 1
    assert fake.payloads[0]["text"] == "oi ios"

    second = client.post("/api/webhooks/imessage", headers=headers, json=payload)
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


def test_telegram_webhook_requires_secret_header(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeTelegramChannel(webhook_mode=True)
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_telegram_channels", lambda: [fake])
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {
            "channels": {
                "telegram": {
                    "webhook_secret": "tg-secret",
                    "rate_limit_per_min": 20,
                }
            }
        },
    )

    resp = client.post(
        "/api/webhooks/telegram",
        json={"update_id": 1, "message": {"text": "oi"}},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized_webhook"


def test_telegram_webhook_processes_payload(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeTelegramChannel(webhook_mode=True)
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_telegram_channels", lambda: [fake])
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {
            "channels": {
                "telegram": {
                    "webhook_secret": "tg-secret",
                    "rate_limit_per_min": 20,
                }
            }
        },
    )

    resp = client.post(
        "/api/webhooks/telegram",
        headers={"x-telegram-bot-api-secret-token": "tg-secret"},
        json={"update_id": 7, "message": {"text": "oi\x00 bot"}},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["processed"] == 1
    assert len(fake.payloads) == 1
    assert fake.payloads[0]["message"]["text"] == "oi bot"


def test_telegram_webhook_rejects_non_webhook_mode(monkeypatch, tmp_path):
    server, webhooks = _boot(monkeypatch, tmp_path)
    client = TestClient(server.app)

    fake = _FakeTelegramChannel(webhook_mode=False)
    webhooks._RATE_STATE.clear()
    monkeypatch.setattr(webhooks, "_resolve_telegram_channels", lambda: [fake])
    monkeypatch.setattr(
        webhooks,
        "load_config",
        lambda: {"channels": {"telegram": {"rate_limit_per_min": 20}}},
    )

    resp = client.post(
        "/api/webhooks/telegram",
        json={"update_id": 1, "message": {"text": "oi"}},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "webhook_mode_disabled"
