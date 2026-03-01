from __future__ import annotations

import asyncio
import unittest
from typing import Any

from clawlite.channels.base import BaseChannel
from clawlite.channels.manager import ChannelManager


class _FakeChannel(BaseChannel):
    def __init__(self, token: str, name: str, **kwargs: Any) -> None:
        super().__init__(name, token, **kwargs)
        self.kwargs = kwargs
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True
        self.running = True

    async def stop(self) -> None:
        self.stopped = True
        self.running = False

    async def send_message(self, session_id: str, text: str) -> None:
        return None


class _FakeOutboundChannel(_FakeChannel):
    def __init__(self, token: str, name: str, outbound: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(token, name, **kwargs)
        self._outbound = dict(outbound)

    def outbound_metrics_snapshot(self) -> dict[str, Any]:
        return dict(self._outbound)


class _CapturingChannel(_FakeChannel):
    def __init__(self, token: str, name: str, **kwargs: Any) -> None:
        super().__init__(token, name, **kwargs)
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, session_id: str, text: str) -> None:
        self.sent.append((session_id, text))


class ChannelManagerTests(unittest.TestCase):
    def test_start_all_uses_accounts_and_channel_specific_kwargs(self) -> None:
        from clawlite.channels import manager as manager_mod

        cfg = {
            "channels": {
                "slack": {
                    "enabled": True,
                    "token": "xoxb-main",
                    "app_token": "xapp-main",
                    "allowFrom": ["U-main"],
                    "allowChannels": ["C-main"],
                    "accounts": [
                        {
                            "account": "workspace-dev",
                            "token": "xoxb-dev",
                            "app_token": "xapp-dev",
                            "allowFrom": ["U-dev"],
                            "allowChannels": ["C-dev"],
                        }
                    ],
                },
                "whatsapp": {
                    "enabled": True,
                    "token": "wa-main-token",
                    "phone_number_id": "1111",
                    "allowFrom": ["+5511999999999"],
                    "accounts": [
                        {
                            "account": "wa-2",
                            "token": "wa-second-token",
                            "phone_number_id": "2222",
                            "allowFrom": ["+5511888888888"],
                        }
                    ],
                },
                "telegram": {
                    "enabled": False,
                    "token": "tg-disabled",
                },
                "googlechat": {
                    "enabled": True,
                    "serviceAccountFile": "/tmp/service-account.json",
                    "botUser": "users/123",
                    "allowFrom": ["users/999"],
                    "allowChannels": ["spaces/AAA"],
                    "requireMention": True,
                    "outboundWebhookUrl": "https://example.test/googlechat",
                    "sendTimeoutSec": 7.0,
                    "sendCircuitFailureThreshold": 4,
                    "sendCircuitCooldownSec": 19.0,
                },
                "irc": {
                    "enabled": True,
                    "host": "irc.libera.chat",
                    "port": 6697,
                    "tls": True,
                    "nick": "clawlite-bot",
                    "channels": ["#clawlite"],
                    "allowFrom": ["alice"],
                    "allowChannels": ["#clawlite"],
                    "requireMention": True,
                    "relay_url": "http://127.0.0.1:8899/irc/send",
                    "sendTimeoutSec": 12.0,
                    "sendCircuitFailureThreshold": 3,
                    "sendCircuitCooldownSec": 17.0,
                },
                "signal": {
                    "enabled": True,
                    "account": "+15551234567",
                    "cliPath": "signal-cli",
                    "allowFrom": ["+15557654321"],
                    "sendTimeoutSec": 20.0,
                    "sendCircuitFailureThreshold": 6,
                    "sendCircuitCooldownSec": 31.0,
                },
                "imessage": {
                    "enabled": True,
                    "cliPath": "imsg",
                    "service": "auto",
                    "allowFrom": ["chat_id:*"],
                    "sendTimeoutSec": 22.0,
                    "sendCircuitFailureThreshold": 7,
                    "sendCircuitCooldownSec": 37.0,
                },
            }
        }

        original_classes = dict(manager_mod.CHANNEL_CLASSES)
        original_load_config = manager_mod.load_config
        try:
            manager_mod.CHANNEL_CLASSES["slack"] = _FakeChannel
            manager_mod.CHANNEL_CLASSES["whatsapp"] = _FakeChannel
            manager_mod.CHANNEL_CLASSES["telegram"] = _FakeChannel
            manager_mod.CHANNEL_CLASSES["googlechat"] = _FakeChannel
            manager_mod.CHANNEL_CLASSES["irc"] = _FakeChannel
            manager_mod.CHANNEL_CLASSES["signal"] = _FakeChannel
            manager_mod.CHANNEL_CLASSES["imessage"] = _FakeChannel
            manager_mod.load_config = lambda: cfg

            cm = ChannelManager()

            async def _run() -> None:
                await cm.start_all()

                self.assertIn("slack", cm.active_channels)
                self.assertIn("slack:workspace-dev", cm.active_channels)
                self.assertIn("whatsapp", cm.active_channels)
                self.assertIn("whatsapp:wa-2", cm.active_channels)
                self.assertIn("googlechat", cm.active_channels)
                self.assertIn("irc", cm.active_channels)
                self.assertIn("signal", cm.active_channels)
                self.assertIn("imessage", cm.active_channels)
                self.assertNotIn("telegram", cm.active_channels)

                slack_main = cm.active_channels["slack"]
                self.assertEqual(slack_main.token, "xoxb-main")
                self.assertEqual(slack_main.kwargs.get("app_token"), "xapp-main")
                self.assertEqual(slack_main.kwargs.get("allowed_channels"), ["C-main"])
                self.assertEqual(slack_main.kwargs.get("allowed_users"), ["U-main"])

                slack_account = cm.active_channels["slack:workspace-dev"]
                self.assertEqual(slack_account.token, "xoxb-dev")
                self.assertEqual(slack_account.kwargs.get("app_token"), "xapp-dev")
                self.assertEqual(slack_account.kwargs.get("allowed_channels"), ["C-dev"])
                self.assertEqual(slack_account.kwargs.get("allowed_users"), ["U-dev"])

                wa_main = cm.active_channels["whatsapp"]
                self.assertEqual(wa_main.kwargs.get("phone_number_id"), "1111")
                self.assertEqual(wa_main.kwargs.get("allowed_numbers"), ["+5511999999999"])

                wa_second = cm.active_channels["whatsapp:wa-2"]
                self.assertEqual(wa_second.kwargs.get("phone_number_id"), "2222")
                self.assertEqual(wa_second.kwargs.get("allowed_numbers"), ["+5511888888888"])

                googlechat = cm.active_channels["googlechat"]
                self.assertEqual(googlechat.kwargs.get("allowed_users"), ["users/999"])
                self.assertEqual(googlechat.kwargs.get("allowed_spaces"), ["spaces/AAA"])
                self.assertEqual(googlechat.kwargs.get("bot_user"), "users/123")
                self.assertEqual(googlechat.kwargs.get("require_mention"), True)
                self.assertEqual(googlechat.kwargs.get("outbound_webhook_url"), "https://example.test/googlechat")
                self.assertEqual(googlechat.kwargs.get("send_timeout_s"), 7.0)
                self.assertEqual(googlechat.kwargs.get("send_circuit_failure_threshold"), 4)
                self.assertEqual(googlechat.kwargs.get("send_circuit_cooldown_s"), 19.0)

                irc = cm.active_channels["irc"]
                self.assertEqual(irc.kwargs.get("host"), "irc.libera.chat")
                self.assertEqual(irc.kwargs.get("nick"), "clawlite-bot")
                self.assertEqual(irc.kwargs.get("allowed_senders"), ["alice"])
                self.assertEqual(irc.kwargs.get("allowed_channels"), ["#clawlite"])
                self.assertEqual(irc.kwargs.get("send_timeout_s"), 12.0)
                self.assertEqual(irc.kwargs.get("send_circuit_failure_threshold"), 3)
                self.assertEqual(irc.kwargs.get("send_circuit_cooldown_s"), 17.0)

                signal = cm.active_channels["signal"]
                self.assertEqual(signal.kwargs.get("account"), "+15551234567")
                self.assertEqual(signal.kwargs.get("cli_path"), "signal-cli")
                self.assertEqual(signal.kwargs.get("allowed_numbers"), ["+15557654321"])
                self.assertEqual(signal.kwargs.get("send_timeout_s"), 20.0)
                self.assertEqual(signal.kwargs.get("send_circuit_failure_threshold"), 6)
                self.assertEqual(signal.kwargs.get("send_circuit_cooldown_s"), 31.0)

                imessage = cm.active_channels["imessage"]
                self.assertEqual(imessage.kwargs.get("cli_path"), "imsg")
                self.assertEqual(imessage.kwargs.get("service"), "auto")
                self.assertEqual(imessage.kwargs.get("allowed_handles"), ["chat_id:*"])
                self.assertEqual(imessage.kwargs.get("send_timeout_s"), 22.0)
                self.assertEqual(imessage.kwargs.get("send_circuit_failure_threshold"), 7)
                self.assertEqual(imessage.kwargs.get("send_circuit_cooldown_s"), 37.0)

                started_channels = list(cm.active_channels.values())
                await cm.stop_all()
                self.assertEqual(cm.active_channels, {})
                for channel in started_channels:
                    self.assertTrue(channel.stopped)

            asyncio.run(_run())
        finally:
            manager_mod.CHANNEL_CLASSES.clear()
            manager_mod.CHANNEL_CLASSES.update(original_classes)
            manager_mod.load_config = original_load_config

    def test_outbound_metrics_aggregation_and_instance_snapshot(self) -> None:
        cm = ChannelManager()
        cm.active_channels = {
            "irc": _FakeOutboundChannel(
                token="",
                name="irc",
                outbound={
                    "sent_ok": 4,
                    "retry_count": 1,
                    "timeout_count": 0,
                    "fallback_count": 1,
                    "send_fail_count": 1,
                    "dedupe_hits": 2,
                    "circuit_open_count": 1,
                    "circuit_half_open_count": 0,
                    "circuit_blocked_count": 2,
                    "circuit_state": "open",
                    "last_success_at": "2026-03-01T11:11:11+00:00",
                },
            ),
            "irc:ops": _FakeOutboundChannel(
                token="",
                name="irc",
                outbound={
                    "sent_ok": 3,
                    "retry_count": 2,
                    "timeout_count": 1,
                    "fallback_count": 1,
                    "send_fail_count": 1,
                    "dedupe_hits": 1,
                    "circuit_open_count": 0,
                    "circuit_half_open_count": 1,
                    "circuit_blocked_count": 1,
                    "circuit_state": "half_open",
                    "last_error": {"provider": "irc-relay-http", "code": "provider_timeout", "reason": "timeout", "attempts": 3, "at": "now"},
                },
            ),
            "telegram": _FakeChannel(token="tok", name="telegram"),
        }
        cm.active_metadata = {
            "irc": {"channel": "irc", "account": ""},
            "irc:ops": {"channel": "irc", "account": "ops"},
            "telegram": {"channel": "telegram", "account": ""},
        }

        aggregated = cm.outbound_metrics()
        self.assertIn("irc", aggregated)
        self.assertEqual(aggregated["irc"]["instances_reporting"], 2)
        self.assertEqual(aggregated["irc"]["sent_ok"], 7)
        self.assertEqual(aggregated["irc"]["retry_count"], 3)
        self.assertEqual(aggregated["irc"]["timeout_count"], 1)
        self.assertEqual(aggregated["irc"]["fallback_count"], 2)
        self.assertEqual(aggregated["irc"]["send_fail_count"], 2)
        self.assertEqual(aggregated["irc"]["dedupe_hits"], 3)
        self.assertEqual(aggregated["irc"]["circuit_open_count"], 1)
        self.assertEqual(aggregated["irc"]["circuit_half_open_count"], 1)
        self.assertEqual(aggregated["irc"]["circuit_blocked_count"], 3)
        self.assertEqual(aggregated["irc"]["circuit_instances_open"], 1)
        self.assertEqual(aggregated["irc"]["circuit_instances_half_open"], 1)
        self.assertEqual(aggregated["irc"]["circuit_state"], "open")
        self.assertIn("last_error", aggregated["irc"])

        instances = cm.describe_instances("irc")
        self.assertEqual(len(instances), 2)
        self.assertIsNotNone(instances[0]["outbound"])
        self.assertIn("sent_ok", instances[0]["outbound"])

    def test_broadcast_proactive_uses_recent_session_or_fallback(self) -> None:
        from clawlite.channels import manager as manager_mod

        cm = ChannelManager()
        tg = _CapturingChannel(token="tok", name="telegram")
        irc = _CapturingChannel(token="tok", name="irc")
        cm.active_channels = {"telegram": tg, "irc": irc}
        cm.active_metadata = {
            "telegram": {"channel": "telegram", "account": ""},
            "irc": {"channel": "irc", "account": ""},
        }
        cm.sessions.bind(instance_key="irc", channel="irc", session_id="irc_group_#ops")

        original_load_config = manager_mod.load_config
        manager_mod.load_config = lambda: {
            "channels": {
                "telegram": {"chat_id": "12345"},
                "irc": {"channels": ["#ops"]},
            }
        }
        try:
            async def _run():
                out = await cm.broadcast_proactive("teste de heartbeat")
                self.assertEqual(out["delivered"], 2)
                self.assertEqual(out["failed"], 0)
                self.assertEqual(out["skipped"], 0)
                self.assertEqual(tg.sent[0][0], "tg_12345")
                self.assertTrue(tg.sent[0][1].startswith("[heartbeat]"))
                self.assertEqual(irc.sent[0][0], "irc_group_#ops")

            asyncio.run(_run())
        finally:
            manager_mod.load_config = original_load_config


if __name__ == "__main__":
    unittest.main()
