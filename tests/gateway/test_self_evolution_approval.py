from __future__ import annotations

import asyncio
from types import SimpleNamespace

from clawlite.bus.events import InboundEvent
from clawlite.gateway.self_evolution_approval import handle_self_evolution_inbound_action


def test_handle_self_evolution_inbound_action_replies_on_telegram() -> None:
    async def _scenario() -> None:
        sent: list[dict[str, object]] = []

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                sent.append(
                    {
                        "channel": channel,
                        "target": target,
                        "text": text,
                        "metadata": dict(metadata or {}),
                    }
                )
                return "ok"

            def get_channel(self, name: str):
                del name
                return None

        evo = SimpleNamespace(
            require_approval=True,
            review_run=lambda run_id, **kwargs: {
                "ok": True,
                "status": "approved",
                "changed": True,
                "run_id": run_id,
                "branch_name": "review/evo-1",
                "commit_sha": "abc123",
                **kwargs,
            },
        )
        event = InboundEvent(
            channel="telegram",
            session_id="telegram:123",
            user_id="42",
            text="self_evolution:approve:evo-1",
            metadata={
                "callback_data": "self_evolution:approve:evo-1",
                "chat_id": "123",
                "message_id": 99,
                "message_thread_id": 7,
                "username": "owner",
            },
        )

        handled = await handle_self_evolution_inbound_action(
            event,
            self_evolution=evo,
            channels=_Channels(),
        )

        assert handled is True
        assert sent[0]["channel"] == "telegram"
        assert sent[0]["target"] == "123"
        assert "approved" in str(sent[0]["text"])
        assert sent[0]["metadata"]["reply_to_message_id"] == 99
        assert sent[0]["metadata"]["message_thread_id"] == 7

    asyncio.run(_scenario())


def test_handle_self_evolution_inbound_action_replies_via_discord_interaction() -> None:
    async def _scenario() -> None:
        replies: list[dict[str, object]] = []

        class _DiscordChannel:
            async def reply_interaction(self, **kwargs):
                replies.append(dict(kwargs))
                return "msg-1"

        class _Channels:
            async def send(self, *, channel: str, target: str, text: str, metadata=None) -> str:
                raise AssertionError("fallback send should not be used")

            def get_channel(self, name: str):
                assert name == "discord"
                return _DiscordChannel()

        evo = SimpleNamespace(
            require_approval=True,
            review_run=lambda run_id, **kwargs: {
                "ok": True,
                "status": "rejected",
                "changed": True,
                "run_id": run_id,
                "branch_name": "review/evo-2",
                "commit_sha": "def456",
                **kwargs,
            },
        )
        event = InboundEvent(
            channel="discord",
            session_id="discord:chan-1",
            user_id="42",
            text="[button:self_evolution:reject:evo-2]",
            metadata={
                "custom_id": "self_evolution:reject:evo-2",
                "interaction_id": "inter-1",
                "interaction_token": "tok-1",
                "channel_id": "chan-1",
                "username": "owner",
            },
        )

        handled = await handle_self_evolution_inbound_action(
            event,
            self_evolution=evo,
            channels=_Channels(),
        )

        assert handled is True
        assert replies[0]["interaction_id"] == "inter-1"
        assert replies[0]["interaction_token"] == "tok-1"
        assert replies[0]["ephemeral"] is True
        assert "rejected" in str(replies[0]["text"])

    asyncio.run(_scenario())


def test_handle_self_evolution_inbound_action_ignores_non_control_messages() -> None:
    async def _scenario() -> None:
        handled = await handle_self_evolution_inbound_action(
            InboundEvent(channel="telegram", session_id="telegram:1", user_id="1", text="hello", metadata={}),
            self_evolution=SimpleNamespace(require_approval=True, review_run=lambda *args, **kwargs: {}),
            channels=SimpleNamespace(send=None, get_channel=lambda _name: None),
        )
        assert handled is False

    asyncio.run(_scenario())
