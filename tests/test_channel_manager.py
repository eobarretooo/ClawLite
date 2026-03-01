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
                },
                "signal": {
                    "enabled": True,
                    "account": "+15551234567",
                    "cliPath": "signal-cli",
                    "allowFrom": ["+15557654321"],
                },
                "imessage": {
                    "enabled": True,
                    "cliPath": "imsg",
                    "service": "auto",
                    "allowFrom": ["chat_id:*"],
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

                irc = cm.active_channels["irc"]
                self.assertEqual(irc.kwargs.get("host"), "irc.libera.chat")
                self.assertEqual(irc.kwargs.get("nick"), "clawlite-bot")
                self.assertEqual(irc.kwargs.get("allowed_senders"), ["alice"])
                self.assertEqual(irc.kwargs.get("allowed_channels"), ["#clawlite"])

                signal = cm.active_channels["signal"]
                self.assertEqual(signal.kwargs.get("account"), "+15551234567")
                self.assertEqual(signal.kwargs.get("cli_path"), "signal-cli")
                self.assertEqual(signal.kwargs.get("allowed_numbers"), ["+15557654321"])

                imessage = cm.active_channels["imessage"]
                self.assertEqual(imessage.kwargs.get("cli_path"), "imsg")
                self.assertEqual(imessage.kwargs.get("service"), "auto")
                self.assertEqual(imessage.kwargs.get("allowed_handles"), ["chat_id:*"])

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


if __name__ == "__main__":
    unittest.main()
