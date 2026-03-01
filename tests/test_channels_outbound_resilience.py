from __future__ import annotations

import asyncio
import logging
import subprocess
import time

from clawlite.channels.googlechat import GoogleChatChannel
from clawlite.channels.imessage import IMessageChannel
from clawlite.channels.irc import IrcChannel
from clawlite.channels.signal import SignalChannel


class _Response:
    def raise_for_status(self) -> None:
        return None


class _GoogleChatOkClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    async def post(self, url: str, json: dict, headers: dict):
        self.calls.append((url, json, headers))
        return _Response()


class _GoogleChatErrorClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def post(self, url: str, json: dict, headers: dict):
        self.calls += 1
        raise self.exc


class _GoogleChatSlowClient:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self.calls = 0

    async def post(self, url: str, json: dict, headers: dict):
        self.calls += 1
        await asyncio.sleep(self.delay_s)
        return _Response()


class _IrcOkClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    async def post(self, url: str, json: dict, headers: dict):
        self.calls.append((url, json, headers))
        return _Response()


class _IrcErrorClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def post(self, url: str, json: dict, headers: dict):
        self.calls += 1
        raise self.exc


class _IrcSlowClient:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self.calls = 0

    async def post(self, url: str, json: dict, headers: dict):
        self.calls += 1
        await asyncio.sleep(self.delay_s)
        return _Response()


def test_googlechat_outbound_ok_and_idempotent():
    channel = GoogleChatChannel(
        token="",
        outbound_webhook_url="https://example.test/chat",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    fake = _GoogleChatOkClient()
    channel._outbound_client = fake

    async def _run() -> None:
        await channel.send_message("gc_dm_spaces_1", "hello")
        await channel.send_message("gc_dm_spaces_1", "hello")

    asyncio.run(_run())
    assert len(fake.calls) == 1
    assert fake.calls[0][1]["text"] == "hello"
    assert "X-Idempotency-Key" in fake.calls[0][2]


def test_googlechat_outbound_retry_exhausted(caplog):
    channel = GoogleChatChannel(
        token="",
        outbound_webhook_url="https://example.test/chat",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    fake = _GoogleChatErrorClient(RuntimeError("relay down"))
    channel._outbound_client = fake
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("gc_dm_spaces_2", "retry me")

    asyncio.run(_run())
    assert fake.calls == 3
    assert "code=provider_send_failed" in caplog.text


def test_googlechat_outbound_timeout(caplog):
    channel = GoogleChatChannel(
        token="",
        outbound_webhook_url="https://example.test/chat",
        send_timeout_s=0.01,
        send_backoff_base_s=0.0,
    )
    fake = _GoogleChatSlowClient(delay_s=0.2)
    channel._outbound_client = fake
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("gc_dm_spaces_3", "slow")

    asyncio.run(_run())
    assert fake.calls == 3
    assert "code=provider_timeout" in caplog.text


def test_googlechat_outbound_fallback_unavailable(caplog):
    channel = GoogleChatChannel(token="")
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("gc_dm_spaces_4", "no webhook")

    asyncio.run(_run())
    assert "code=channel_unavailable" in caplog.text


def test_irc_outbound_ok_and_idempotent():
    channel = IrcChannel(
        token="",
        relay_url="https://example.test/irc",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    fake = _IrcOkClient()
    channel._relay_client = fake

    async def _run() -> None:
        await channel.send_message("irc_dm_alice", "pong")
        await channel.send_message("irc_dm_alice", "pong")

    asyncio.run(_run())
    assert len(fake.calls) == 1
    assert fake.calls[0][1]["target"] == "alice"
    assert fake.calls[0][1]["text"] == "pong"
    assert fake.calls[0][1]["idempotency_key"]


def test_irc_outbound_retry_exhausted(caplog):
    channel = IrcChannel(
        token="",
        relay_url="https://example.test/irc",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    fake = _IrcErrorClient(RuntimeError("relay down"))
    channel._relay_client = fake
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("irc_dm_alice", "retry")

    asyncio.run(_run())
    assert fake.calls == 3
    assert "code=provider_send_failed" in caplog.text


def test_irc_outbound_timeout(caplog):
    channel = IrcChannel(
        token="",
        relay_url="https://example.test/irc",
        send_timeout_s=0.01,
        send_backoff_base_s=0.0,
    )
    fake = _IrcSlowClient(delay_s=0.2)
    channel._relay_client = fake
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("irc_dm_alice", "slow")

    asyncio.run(_run())
    assert fake.calls == 3
    assert "code=provider_timeout" in caplog.text


def test_irc_outbound_fallback_unavailable(caplog):
    channel = IrcChannel(token="")
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("irc_dm_alice", "no relay")

    asyncio.run(_run())
    assert "code=channel_unavailable" in caplog.text


def test_signal_outbound_ok_and_idempotent(monkeypatch):
    channel = SignalChannel(
        token="",
        cli_path="signal-cli",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    monkeypatch.setattr("clawlite.channels.signal.shutil.which", lambda _name: "/usr/bin/signal-cli")
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("clawlite.channels.signal.subprocess.run", _fake_run)

    async def _run() -> None:
        await channel.send_message("signal_dm_+15551234567", "hello signal")
        await channel.send_message("signal_dm_+15551234567", "hello signal")

    asyncio.run(_run())
    assert len(calls) == 1
    assert calls[0][-1] == "+15551234567"


def test_signal_outbound_retry_exhausted(monkeypatch, caplog):
    channel = SignalChannel(
        token="",
        cli_path="signal-cli",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    monkeypatch.setattr("clawlite.channels.signal.shutil.which", lambda _name: "/usr/bin/signal-cli")
    calls = {"count": 0}
    caplog.set_level(logging.ERROR)

    def _fake_run(cmd, **kwargs):
        calls["count"] += 1
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="signal failed")

    monkeypatch.setattr("clawlite.channels.signal.subprocess.run", _fake_run)

    async def _run() -> None:
        await channel.send_message("signal_dm_+15551234567", "retry")

    asyncio.run(_run())
    assert calls["count"] == 3
    assert "code=provider_send_failed" in caplog.text


def test_signal_outbound_timeout(monkeypatch, caplog):
    channel = SignalChannel(
        token="",
        cli_path="signal-cli",
        send_timeout_s=0.01,
        send_backoff_base_s=0.0,
    )
    monkeypatch.setattr("clawlite.channels.signal.shutil.which", lambda _name: "/usr/bin/signal-cli")
    calls = {"count": 0}
    caplog.set_level(logging.ERROR)

    def _fake_run(cmd, **kwargs):
        calls["count"] += 1
        time.sleep(0.2)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("clawlite.channels.signal.subprocess.run", _fake_run)

    async def _run() -> None:
        await channel.send_message("signal_dm_+15551234567", "slow")

    asyncio.run(_run())
    assert calls["count"] == 3
    assert "code=provider_timeout" in caplog.text


def test_signal_outbound_fallback_unavailable(monkeypatch, caplog):
    channel = SignalChannel(token="", cli_path="missing-signal-cli")
    monkeypatch.setattr("clawlite.channels.signal.shutil.which", lambda _name: None)
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("signal_dm_+15551234567", "no cli")

    asyncio.run(_run())
    assert "code=channel_unavailable" in caplog.text


def test_imessage_outbound_ok_and_idempotent(monkeypatch):
    channel = IMessageChannel(
        token="",
        cli_path="imsg",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    monkeypatch.setattr("clawlite.channels.imessage.shutil.which", lambda _name: "/usr/bin/imsg")
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("clawlite.channels.imessage.subprocess.run", _fake_run)

    async def _run() -> None:
        await channel.send_message("imessage_dm_user_icloud_com", "hello imessage")
        await channel.send_message("imessage_dm_user_icloud_com", "hello imessage")

    asyncio.run(_run())
    assert len(calls) == 1
    assert calls[0][0] == "imsg"


def test_imessage_outbound_retry_exhausted(monkeypatch, caplog):
    channel = IMessageChannel(
        token="",
        cli_path="imsg",
        send_timeout_s=0.1,
        send_backoff_base_s=0.0,
    )
    monkeypatch.setattr("clawlite.channels.imessage.shutil.which", lambda _name: "/usr/bin/imsg")
    calls = {"count": 0}
    caplog.set_level(logging.ERROR)

    def _fake_run(cmd, **kwargs):
        calls["count"] += 1
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="imsg failed")

    monkeypatch.setattr("clawlite.channels.imessage.subprocess.run", _fake_run)

    async def _run() -> None:
        await channel.send_message("imessage_dm_user_icloud_com", "retry")

    asyncio.run(_run())
    assert calls["count"] == 3
    assert "code=provider_send_failed" in caplog.text


def test_imessage_outbound_timeout(monkeypatch, caplog):
    channel = IMessageChannel(
        token="",
        cli_path="imsg",
        send_timeout_s=0.01,
        send_backoff_base_s=0.0,
    )
    monkeypatch.setattr("clawlite.channels.imessage.shutil.which", lambda _name: "/usr/bin/imsg")
    calls = {"count": 0}
    caplog.set_level(logging.ERROR)

    def _fake_run(cmd, **kwargs):
        calls["count"] += 1
        time.sleep(0.2)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("clawlite.channels.imessage.subprocess.run", _fake_run)

    async def _run() -> None:
        await channel.send_message("imessage_dm_user_icloud_com", "slow")

    asyncio.run(_run())
    assert calls["count"] == 3
    assert "code=provider_timeout" in caplog.text


def test_imessage_outbound_fallback_unavailable(monkeypatch, caplog):
    channel = IMessageChannel(token="", cli_path="missing-imsg")
    monkeypatch.setattr("clawlite.channels.imessage.shutil.which", lambda _name: None)
    caplog.set_level(logging.ERROR)

    async def _run() -> None:
        await channel.send_message("imessage_dm_user_icloud_com", "no cli")

    asyncio.run(_run())
    assert "code=channel_unavailable" in caplog.text
