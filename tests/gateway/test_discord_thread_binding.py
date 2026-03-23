from __future__ import annotations

import asyncio

from clawlite.bus.events import InboundEvent
from clawlite.gateway.discord_thread_binding import (
    handle_discord_thread_binding_inbound_action,
)


def test_handle_discord_thread_binding_focus_replies_via_interaction() -> None:
    async def _scenario() -> None:
        replies: list[dict[str, object]] = []
        calls: list[dict[str, object]] = []

        class _DiscordChannel:
            async def bind_thread(self, **kwargs):
                calls.append(dict(kwargs))
                return {"ok": True, "changed": True}

            async def reply_interaction(self, **kwargs):
                replies.append(dict(kwargs))
                return "msg-1"

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                raise AssertionError("interaction reply should be used")

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:thread-1",
                user_id="user-1",
                text="/focus discord:guild:guild-main:channel:chan-main",
                metadata={
                    "channel_id": "thread-1",
                    "guild_id": "guild-1",
                    "interaction_id": "inter-1",
                    "interaction_token": "tok-1",
                },
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert calls[0]["channel_id"] == "thread-1"
        assert calls[0]["session_id"] == "discord:guild:guild-main:channel:chan-main"
        assert replies[0]["ephemeral"] is True
        assert "Focused this Discord channel" in str(replies[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_unfocus_falls_back_to_channel_send() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _DiscordChannel:
            async def unbind_thread(self, **kwargs):
                assert kwargs["channel_id"] == "thread-2"
                return {"ok": True, "changed": True}

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append(
                    {
                        "channel": channel,
                        "target": target,
                        "text": text,
                    }
                )
                return "ok"

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:thread-2",
                user_id="user-2",
                text="/unfocus",
                metadata={"channel_id": "thread-2", "guild_id": "guild-1"},
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert sent[0]["channel"] == "discord"
        assert sent[0]["target"] == "thread-2"
        assert "Removed the focus binding" in str(sent[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_ignores_non_control_messages() -> None:
    async def _scenario() -> None:
        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="hello",
                metadata={"channel_id": "chan-1"},
            ),
            channels=type(
                "_Channels",
                (),
                {
                    "send": None,
                    "get_channel": lambda self, _name: None,
                },
            )(),
        )
        assert handled is False

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_reports_operator_status() -> None:
    async def _scenario() -> None:
        replies: list[dict[str, object]] = []

        class _DiscordChannel:
            def operator_status(self):
                return {
                    "connected": True,
                    "gateway_task_state": "running",
                    "heartbeat_task_state": "running",
                    "gateway_session_task_state": "stopped",
                    "gateway_session_waiting_for": "",
                    "gateway_reconnect_attempt": 0,
                    "gateway_reconnect_retry_in_s": 0.0,
                    "gateway_reconnect_state": "idle",
                    "policy_allowed_count": 4,
                    "policy_blocked_count": 1,
                    "thread_binding_count": 2,
                    "last_error": "",
                }

            async def reply_interaction(self, **kwargs):
                replies.append(dict(kwargs))
                return "msg-2"

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                raise AssertionError("interaction reply should be used")

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-status",
                metadata={
                    "channel_id": "chan-1",
                    "interaction_id": "inter-2",
                    "interaction_token": "tok-2",
                },
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "Discord operator status" in str(replies[0]["text"])
        assert "session_watchdog: stopped" in str(replies[0]["text"])
        assert "focus bindings: 2" in str(replies[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_reports_pending_gateway_session_status() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _DiscordChannel:
            def operator_status(self):
                return {
                    "connected": True,
                    "gateway_task_state": "running",
                    "heartbeat_task_state": "running",
                    "gateway_session_task_state": "running",
                    "gateway_session_waiting_for": "resumed",
                    "gateway_reconnect_attempt": 0,
                    "gateway_reconnect_retry_in_s": 0.0,
                    "gateway_reconnect_state": "idle",
                    "policy_allowed_count": 4,
                    "policy_blocked_count": 1,
                    "thread_binding_count": 2,
                    "last_error": "",
                }

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append({"channel": channel, "target": target, "text": text})
                return "ok"

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-status",
                metadata={"channel_id": "chan-1"},
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "session_watchdog: running" in str(sent[0]["text"])
        assert "waiting_for: RESUMED" in str(sent[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_reports_reconnect_backoff() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _DiscordChannel:
            def operator_status(self):
                return {
                    "connected": False,
                    "gateway_task_state": "running",
                    "heartbeat_task_state": "stopped",
                    "gateway_session_task_state": "stopped",
                    "gateway_session_waiting_for": "",
                    "gateway_reconnect_attempt": 2,
                    "gateway_reconnect_retry_in_s": 3.5,
                    "gateway_reconnect_state": "backoff",
                    "policy_allowed_count": 4,
                    "policy_blocked_count": 1,
                    "thread_binding_count": 2,
                    "last_error": "gateway connect failed",
                }

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append({"channel": channel, "target": target, "text": text})
                return "ok"

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-status",
                metadata={"channel_id": "chan-1"},
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "reconnect: attempt 2 | retry_in 3.5s" in str(sent[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_reports_active_reconnect_without_backoff() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _DiscordChannel:
            def operator_status(self):
                return {
                    "connected": False,
                    "gateway_task_state": "running",
                    "heartbeat_task_state": "stopped",
                    "gateway_session_task_state": "stopped",
                    "gateway_session_waiting_for": "",
                    "gateway_reconnect_attempt": 3,
                    "gateway_reconnect_retry_in_s": 0.0,
                    "gateway_reconnect_state": "retrying",
                    "policy_allowed_count": 4,
                    "policy_blocked_count": 1,
                    "thread_binding_count": 2,
                    "last_error": "gateway connect failed",
                }

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append({"channel": channel, "target": target, "text": text})
                return "ok"

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-status",
                metadata={"channel_id": "chan-1"},
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "reconnect: attempt 3 | retrying now" in str(sent[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_reports_lifecycle_history() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _DiscordChannel:
            def operator_status(self):
                return {
                    "connected": False,
                    "gateway_task_state": "running",
                    "heartbeat_task_state": "stopped",
                    "gateway_session_task_state": "stopped",
                    "gateway_session_waiting_for": "",
                    "gateway_reconnect_attempt": 0,
                    "gateway_reconnect_retry_in_s": 0.0,
                    "gateway_reconnect_state": "idle",
                    "gateway_last_connect_at": "2026-03-23T12:10:00+00:00",
                    "gateway_last_ready_at": "2026-03-23T12:10:03+00:00",
                    "gateway_last_disconnect_at": "2026-03-23T12:11:00+00:00",
                    "gateway_last_disconnect_reason": "discord_gateway_reconnect_requested",
                    "gateway_last_lifecycle_outcome": "disconnected",
                    "gateway_last_lifecycle_at": "2026-03-23T12:11:00+00:00",
                    "policy_allowed_count": 4,
                    "policy_blocked_count": 1,
                    "thread_binding_count": 2,
                    "last_error": "gateway connect failed",
                }

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append({"channel": channel, "target": target, "text": text})
                return "ok"

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-status",
                metadata={"channel_id": "chan-1"},
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "lifecycle: disconnected @ 2026-03-23T12:11:00+00:00" in str(sent[0]["text"])
        assert "last_connect_at: 2026-03-23T12:10:00+00:00" in str(sent[0]["text"])
        assert "last_ready_at: 2026-03-23T12:10:03+00:00" in str(sent[0]["text"])
        assert "last_disconnect_at: 2026-03-23T12:11:00+00:00" in str(sent[0]["text"])
        assert "disconnect_reason: discord_gateway_reconnect_requested" in str(sent[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_refreshes_transport() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _DiscordChannel:
            async def operator_refresh_transport(self):
                return {
                    "ok": True,
                    "gateway_restarted": True,
                    "status": {
                        "connected": False,
                        "gateway_task_state": "running",
                        "last_error": "",
                    },
                }

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append({"channel": channel, "target": target, "text": text})
                return "ok"

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-refresh",
                metadata={"channel_id": "chan-1"},
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "Discord transport refresh completed" in str(sent[0]["text"])
        assert "gateway_restarted: True" in str(sent[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_reports_presence_status() -> None:
    async def _scenario() -> None:
        replies: list[dict[str, object]] = []

        class _DiscordChannel:
            def operator_status(self):
                return {
                    "auto_presence_enabled": True,
                    "presence_last_state": "healthy",
                    "presence_status": "idle",
                    "presence_activity": "Focus time",
                    "auto_presence_task_state": "running",
                    "presence_last_error": "",
                }

            async def reply_interaction(self, **kwargs):
                replies.append(dict(kwargs))
                return "msg-2"

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                raise AssertionError("interaction reply should be used")

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-presence",
                metadata={
                    "channel_id": "chan-1",
                    "interaction_id": "inter-2",
                    "interaction_token": "tok-2",
                },
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "Discord presence status" in str(replies[0]["text"])
        assert "auto_presence_enabled: True" in str(replies[0]["text"])

    asyncio.run(_scenario())


def test_handle_discord_thread_binding_refreshes_presence() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _DiscordChannel:
            async def operator_refresh_presence(self):
                return {
                    "ok": True,
                    "sent": True,
                    "reason": "updated",
                    "status": {
                        "presence_last_state": "healthy",
                        "presence_last_error": "",
                    },
                }

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append({"channel": channel, "target": target, "text": text})
                return "ok"

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        handled = await handle_discord_thread_binding_inbound_action(
            InboundEvent(
                channel="discord",
                session_id="discord:guild:guild-1:channel:chan-1",
                user_id="user-1",
                text="/discord-presence-refresh",
                metadata={"channel_id": "chan-1"},
            ),
            channels=_Channels(),
        )

        assert handled is True
        assert "Discord presence refresh completed" in str(sent[0]["text"])
        assert "sent: True" in str(sent[0]["text"])

    asyncio.run(_scenario())
