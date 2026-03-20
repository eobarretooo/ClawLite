from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import clawlite.channels.telegram as telegram_module
from clawlite.channels.telegram import markdown_to_telegram_html
from clawlite.channels.telegram import split_message
from clawlite.channels.telegram import TelegramCircuitOpenError
from clawlite.channels.telegram import TelegramChannel
from clawlite.channels.telegram_offset_store import TelegramOffsetStore


def _bind_offset_path(channel: TelegramChannel, path: Path) -> None:
    channel._offset_store.path = path
    channel._offset = channel._load_offset()


def test_telegram_split_message_chunking() -> None:
    text = "a" * 9000
    chunks = split_message(text, max_len=4000)
    assert len(chunks) == 3
    assert sum(len(c) for c in chunks) == 9000
    assert all(len(c) <= 4000 for c in chunks)


def test_telegram_allow_from_empty_allows_anyone() -> None:
    channel = TelegramChannel(config={"token": "x:token", "allowFrom": []})
    assert channel._is_allowed_sender("123")
    assert channel._is_allowed_sender("999", "alice")


def test_telegram_allow_from_blocks_not_listed() -> None:
    channel = TelegramChannel(
        config={"token": "x:token", "allowFrom": ["123", "@owner"]}
    )
    assert channel._is_allowed_sender("123")
    assert channel._is_allowed_sender("777", "owner")
    assert not channel._is_allowed_sender("777", "guest")


def test_telegram_missing_dependency_reports_extra(monkeypatch) -> None:
    async def _scenario() -> None:
        monkeypatch.setitem(sys.modules, "telegram", None)
        channel = TelegramChannel(config={"token": "x:token"})
        try:
            await channel._ensure_bot()
            raise AssertionError("expected missing telegram dependency")
        except RuntimeError as exc:
            assert 'clawlite[telegram]' in str(exc)

    asyncio.run(_scenario())


def test_telegram_dm_policy_disabled_blocks_private_message() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "dm_policy": "disabled"},
            on_message=_on_message,
        )
        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=SimpleNamespace(type="private"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert emitted == []
        signals = channel.signals()
        assert signals["policy_blocked_count"] == 1
        assert signals["policy_allowed_count"] == 0

    asyncio.run(_scenario())


def test_telegram_dm_allowlist_policy_allows_listed_user_and_blocks_others() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dm_policy": "allowlist",
                "dm_allow_from": ["123", "@owner"],
            },
            on_message=_on_message,
        )
        allowed_message = SimpleNamespace(
            text="allowed",
            caption=None,
            chat_id=11,
            from_user=SimpleNamespace(
                id=123, username="owner", first_name="Owner", language_code="en"
            ),
            message_id=10,
            chat=SimpleNamespace(type="private"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        blocked_message = SimpleNamespace(
            text="blocked",
            caption=None,
            chat_id=12,
            from_user=SimpleNamespace(
                id=999, username="guest", first_name="Guest", language_code="en"
            ),
            message_id=11,
            chat=SimpleNamespace(type="private"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        await channel._handle_update(
            SimpleNamespace(
                update_id=101,
                message=allowed_message,
                edited_message=None,
                effective_message=allowed_message,
            )
        )
        await channel._handle_update(
            SimpleNamespace(
                update_id=102,
                message=blocked_message,
                edited_message=None,
                effective_message=blocked_message,
            )
        )

        assert len(emitted) == 1
        assert emitted[0][1] == "123"
        signals = channel.signals()
        assert signals["policy_allowed_count"] == 1
        assert signals["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_dm_policy_pairing_blocks_private_message_and_sends_pairing_notice(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dm_policy": "pairing",
                "pairing_state_path": str(tmp_path / "telegram-pairing.json"),
            },
            on_message=_on_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.sent: list[dict] = []

            async def send_message(self, **kwargs):
                self.sent.append(kwargs)
                return SimpleNamespace(message_id=len(self.sent))

        bot = FakeBot()
        channel.bot = bot
        user = SimpleNamespace(
            id=321, username="guest", first_name="Guest", language_code="en"
        )
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=55,
            from_user=user,
            message_id=10,
            chat=SimpleNamespace(type="private"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=120,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert emitted == []
        assert len(bot.sent) == 1
        sent_text = str(bot.sent[0]["text"])
        assert "Pairing code:" in sent_text
        assert "clawlite pairing approve telegram" in sent_text
        signals = channel.signals()
        assert signals["policy_blocked_count"] == 1
        assert signals["policy_allowed_count"] == 0
        assert signals["pairing_required_count"] == 1
        assert signals["pairing_request_created_count"] == 1
        assert signals["pairing_notice_sent_count"] == 1

    asyncio.run(_scenario())


def test_telegram_dm_policy_pairing_allows_after_approval(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dm_policy": "pairing",
                "pairing_state_path": str(tmp_path / "telegram-pairing.json"),
            },
            on_message=_on_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.sent: list[dict] = []

            async def send_message(self, **kwargs):
                self.sent.append(kwargs)
                return SimpleNamespace(message_id=len(self.sent))

        bot = FakeBot()
        channel.bot = bot
        user = SimpleNamespace(
            id=321, username="guest", first_name="Guest", language_code="en"
        )
        chat = SimpleNamespace(type="private")

        first_message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=55,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        first_update = SimpleNamespace(
            update_id=121,
            message=first_message,
            edited_message=None,
            effective_message=first_message,
        )

        await channel._handle_update(first_update)

        pending = channel._pairing_store.list_pending()
        assert len(pending) == 1
        code = str(pending[0]["code"])
        approved = channel._pairing_store.approve(code)
        assert approved is not None

        second_message = SimpleNamespace(
            text="hello again",
            caption=None,
            chat_id=55,
            from_user=user,
            message_id=11,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        second_update = SimpleNamespace(
            update_id=122,
            message=second_message,
            edited_message=None,
            effective_message=second_message,
        )

        processed = await channel._handle_update(second_update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:55"
        assert user_id == "321"
        assert text == "hello again"
        assert metadata["channel"] == "telegram"
        signals = channel.signals()
        assert signals["policy_blocked_count"] == 1
        assert signals["policy_allowed_count"] == 1
        assert signals["pairing_required_count"] == 1

    asyncio.run(_scenario())


def test_telegram_group_policy_disabled_blocks_group_message() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "group_policy": "disabled"},
            on_message=_on_message,
        )
        message = SimpleNamespace(
            text="group",
            caption=None,
            chat_id=-1001,
            from_user=SimpleNamespace(
                id=55, username="alice", first_name="Alice", language_code="en"
            ),
            message_id=10,
            chat=SimpleNamespace(type="group"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        processed = await channel._handle_update(
            SimpleNamespace(
                update_id=103,
                message=message,
                edited_message=None,
                effective_message=message,
            )
        )

        assert processed is True
        assert emitted == []
        assert channel.signals()["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_topic_allowlist_policy_allows_listed_thread_user_and_blocks_nonlisted() -> (
    None
):
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "topic_policy": "allowlist",
                "topic_allow_from": ["@alice"],
            },
            on_message=_on_message,
        )
        allowed_message = SimpleNamespace(
            text="thread allowed",
            caption=None,
            chat_id=-1002,
            message_thread_id=7,
            from_user=SimpleNamespace(
                id=1, username="alice", first_name="Alice", language_code="en"
            ),
            message_id=20,
            chat=SimpleNamespace(type="supergroup"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        blocked_message = SimpleNamespace(
            text="thread blocked",
            caption=None,
            chat_id=-1002,
            message_thread_id=7,
            from_user=SimpleNamespace(
                id=2, username="bob", first_name="Bob", language_code="en"
            ),
            message_id=21,
            chat=SimpleNamespace(type="supergroup"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        await channel._handle_update(
            SimpleNamespace(
                update_id=104,
                message=allowed_message,
                edited_message=None,
                effective_message=allowed_message,
            )
        )
        await channel._handle_update(
            SimpleNamespace(
                update_id=105,
                message=blocked_message,
                edited_message=None,
                effective_message=blocked_message,
            )
        )

        assert len(emitted) == 1
        assert emitted[0][1] == "1"
        signals = channel.signals()
        assert signals["policy_allowed_count"] == 1
        assert signals["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_group_override_supersedes_base_group_and_topic_policy() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "group_policy": "disabled",
                "topic_policy": "disabled",
                "group_overrides": {
                    "-1009": {
                        "policy": "open",
                        "topics": {
                            "7": {
                                "policy": "allowlist",
                                "allow_from": ["@alice"],
                            }
                        },
                    }
                },
            },
            on_message=_on_message,
        )
        group_message = SimpleNamespace(
            text="group override open",
            caption=None,
            chat_id=-1009,
            from_user=SimpleNamespace(
                id=22, username="guest", first_name="Guest", language_code="en"
            ),
            message_id=31,
            chat=SimpleNamespace(type="group"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        topic_allowed_message = SimpleNamespace(
            text="topic allowed",
            caption=None,
            chat_id=-1009,
            message_thread_id=7,
            from_user=SimpleNamespace(
                id=1, username="alice", first_name="Alice", language_code="en"
            ),
            message_id=32,
            chat=SimpleNamespace(type="supergroup"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        topic_blocked_message = SimpleNamespace(
            text="topic blocked",
            caption=None,
            chat_id=-1009,
            message_thread_id=7,
            from_user=SimpleNamespace(
                id=2, username="bob", first_name="Bob", language_code="en"
            ),
            message_id=33,
            chat=SimpleNamespace(type="supergroup"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        await channel._handle_update(
            SimpleNamespace(
                update_id=106,
                message=group_message,
                edited_message=None,
                effective_message=group_message,
            )
        )
        await channel._handle_update(
            SimpleNamespace(
                update_id=107,
                message=topic_allowed_message,
                edited_message=None,
                effective_message=topic_allowed_message,
            )
        )
        await channel._handle_update(
            SimpleNamespace(
                update_id=108,
                message=topic_blocked_message,
                edited_message=None,
                effective_message=topic_blocked_message,
            )
        )

        assert len(emitted) == 2
        assert [entry[2] for entry in emitted] == [
            "group override open",
            "topic allowed",
        ]
        signals = channel.signals()
        assert signals["policy_allowed_count"] == 2
        assert signals["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_business_message_is_forwarded_with_business_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token"},
            on_message=_on_message,
        )
        message = SimpleNamespace(
            text="business hello",
            caption=None,
            chat_id=6001,
            business_connection_id="bc-1",
            from_user=SimpleNamespace(
                id=77, username="merchant", first_name="Merchant", language_code="en"
            ),
            message_id=501,
            chat=SimpleNamespace(type="private"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=601,
            message=None,
            edited_message=None,
            business_message=message,
            edited_business_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:6001"
        assert user_id == "77"
        assert text == "business hello"
        assert metadata["update_kind"] == "business_message"
        assert metadata["business_connection_id"] == "bc-1"
        assert metadata["message_id"] == 501

    asyncio.run(_scenario())


def test_telegram_edited_business_message_marks_edit_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token"},
            on_message=_on_message,
        )
        message = SimpleNamespace(
            text="business edited",
            caption=None,
            chat_id=6002,
            business_connection_id="bc-2",
            from_user=SimpleNamespace(
                id=88, username="agent", first_name="Agent", language_code="en"
            ),
            message_id=502,
            chat=SimpleNamespace(type="private"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=602,
            message=None,
            edited_message=None,
            business_message=None,
            edited_business_message=message,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        metadata = emitted[0][3]
        assert metadata["update_kind"] == "edited_business_message"
        assert metadata["is_edit"] is True
        assert metadata["business_connection_id"] == "bc-2"

    asyncio.run(_scenario())


def test_telegram_inline_query_is_answered_with_empty_results() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.inline_answers: list[dict] = []

            async def answer_inline_query(self, **kwargs):
                self.inline_answers.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot
        update = SimpleNamespace(
            update_id=603,
            inline_query=SimpleNamespace(id="iq-1", query="hello"),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(bot.inline_answers) == 1
        assert bot.inline_answers[0]["inline_query_id"] == "iq-1"
        assert bot.inline_answers[0]["results"] == []
        signals = channel.signals()
        assert signals["inline_query_received_count"] == 1
        assert signals["inline_query_answered_count"] == 1
        assert signals["inline_query_answer_error_count"] == 0

    asyncio.run(_scenario())


def test_telegram_payment_queries_are_rejected_when_payments_are_unsupported() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.shipping_answers: list[dict] = []
                self.pre_checkout_answers: list[dict] = []

            async def answer_shipping_query(self, **kwargs):
                self.shipping_answers.append(kwargs)
                return True

            async def answer_pre_checkout_query(self, **kwargs):
                self.pre_checkout_answers.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        shipping_processed = await channel._handle_update(
            SimpleNamespace(
                update_id=604,
                shipping_query=SimpleNamespace(id="ship-1"),
                message=None,
                edited_message=None,
                effective_message=None,
            )
        )
        checkout_processed = await channel._handle_update(
            SimpleNamespace(
                update_id=605,
                pre_checkout_query=SimpleNamespace(id="checkout-1"),
                message=None,
                edited_message=None,
                effective_message=None,
            )
        )

        assert shipping_processed is True
        assert checkout_processed is True
        assert bot.shipping_answers[0]["shipping_query_id"] == "ship-1"
        assert bot.shipping_answers[0]["ok"] is False
        assert bot.pre_checkout_answers[0]["pre_checkout_query_id"] == "checkout-1"
        assert bot.pre_checkout_answers[0]["ok"] is False
        signals = channel.signals()
        assert signals["shipping_query_received_count"] == 1
        assert signals["shipping_query_rejected_count"] == 1
        assert signals["pre_checkout_query_received_count"] == 1
        assert signals["pre_checkout_query_rejected_count"] == 1

    asyncio.run(_scenario())


def test_telegram_my_chat_member_updates_connection_state() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        connected_update = SimpleNamespace(
            update_id=606,
            my_chat_member=SimpleNamespace(
                new_chat_member=SimpleNamespace(status="administrator")
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )
        blocked_update = SimpleNamespace(
            update_id=607,
            my_chat_member=SimpleNamespace(
                new_chat_member=SimpleNamespace(status="kicked")
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        assert await channel._handle_update(connected_update) is True
        assert channel._connected is True
        assert await channel._handle_update(blocked_update) is True
        assert channel._connected is False
        assert channel.signals()["my_chat_member_received_count"] == 2

    asyncio.run(_scenario())


def test_telegram_callback_query_policy_blocked_when_context_denies() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "group_policy": "disabled"},
            on_message=_on_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.acks: list[dict] = []

            async def answer_callback_query(self, **kwargs):
                self.acks.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot
        callback_query = SimpleNamespace(
            id="cq-policy",
            data="action:block",
            chat_instance="inst",
            from_user=SimpleNamespace(id=9, username="guest"),
            message=SimpleNamespace(
                message_id=70,
                chat=SimpleNamespace(id=-10010, type="group"),
                chat_id=-10010,
            ),
        )

        processed = await channel._handle_update(
            SimpleNamespace(
                update_id=109,
                callback_query=callback_query,
                message=None,
                edited_message=None,
                effective_message=None,
            )
        )

        assert processed is True
        assert emitted == []
        assert len(bot.acks) == 1
        signals = channel.signals()
        assert signals["callback_query_blocked_count"] == 1
        assert signals["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_message_reaction_policy_blocked_when_context_denies() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "reaction_notifications": "all",
                "group_policy": "disabled",
            },
            on_message=_on_message,
        )
        update = SimpleNamespace(
            update_id=110,
            callback_query=None,
            message_reaction=SimpleNamespace(
                chat=SimpleNamespace(id=-10011, type="group"),
                message_id=99,
                user=SimpleNamespace(id=9, username="guest", is_bot=False),
                old_reaction=[],
                new_reaction=[SimpleNamespace(emoji="🔥")],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert emitted == []
        signals = channel.signals()
        assert signals["message_reaction_blocked_count"] == 1
        assert signals["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_drop_pending_updates_on_startup(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={"token": "x:token", "drop_pending_updates": True}
        )
        offset_path = tmp_path / "offset.json"
        _bind_offset_path(channel, offset_path)

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def get_updates(self, *, offset, timeout, allowed_updates):
                self.calls += 1
                if self.calls == 1:
                    return [
                        SimpleNamespace(update_id=12),
                        SimpleNamespace(update_id=13),
                    ]
                return []

        channel.bot = FakeBot()
        channel._offset = 0
        await channel._drop_pending_updates()

        assert channel._offset == 14
        persisted = json.loads(offset_path.read_text(encoding="utf-8"))
        assert persisted["safe_update_id"] == 13
        assert persisted["next_offset"] == 14

    asyncio.run(_scenario())


def test_telegram_start_resets_startup_drop_state_for_reuse() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={"token": "x:token", "drop_pending_updates": True}
        )
        channel._startup_drop_done = True
        observed_states: list[bool] = []

        async def _fake_poll_loop() -> None:
            observed_states.append(channel._startup_drop_done)
            channel._running = False

        channel._poll_loop = _fake_poll_loop  # type: ignore[method-assign]
        await channel.start()
        assert channel._task is not None
        await channel._task

        assert observed_states == [False]

        channel._startup_drop_done = True
        await channel.stop()
        assert channel._startup_drop_done is False

    asyncio.run(_scenario())


def test_telegram_command_help_is_handled_locally(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.sent: list[dict] = []

            async def send_message(self, **kwargs):
                self.sent.append(kwargs)

        bot = FakeBot()
        channel.bot = bot

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="/help",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(bot.sent) == 1
        assert "ClawLite commands" in bot.sent[0]["text"]
        assert emitted == []

    asyncio.run(_scenario())


def test_telegram_command_stop_is_forwarded_with_metadata(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="/stop",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:42"
        assert user_id == "1"
        assert text == "/stop"
        assert metadata["is_command"] is True
        assert metadata["command"] == "stop"
        assert metadata["channel"] == "telegram"

    asyncio.run(_scenario())


def test_telegram_edited_message_duplicate_is_deduped(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        base = {
            "caption": None,
            "chat_id": 42,
            "from_user": user,
            "message_id": 10,
            "chat": chat,
            "date": None,
            "edit_date": None,
            "reply_to_message": None,
        }
        message = SimpleNamespace(text="hello", **base)
        edited_same = SimpleNamespace(text="hello", **base)

        update_message = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )
        update_edit = SimpleNamespace(
            update_id=101,
            message=None,
            edited_message=edited_same,
            effective_message=edited_same,
        )

        await channel._handle_update(update_message)
        await channel._handle_update(update_edit)

        assert len(emitted) == 1
        assert emitted[0][2] == "hello"
        assert emitted[0][3]["is_edit"] is False

    asyncio.run(_scenario())


def test_telegram_reply_metadata_is_emitted(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        reply_user = SimpleNamespace(id=9, username="bob")
        reply_to = SimpleNamespace(
            message_id=3, text="parent", caption=None, from_user=reply_user
        )
        chat = SimpleNamespace(type="group")
        message = SimpleNamespace(
            text="child",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=reply_to,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        metadata = emitted[0][3]
        assert metadata["reply_to_message_id"] == 3
        assert metadata["reply_to_user_id"] == 9
        assert metadata["reply_to_username"] == "bob"
        assert metadata["reply_to_text"] == "parent"
        assert metadata["is_group"] is True

    asyncio.run(_scenario())


def test_telegram_inbound_metadata_includes_message_thread_id() -> None:
    async def _scenario() -> None:
        emitted: list[dict] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, text
            emitted.append(metadata)

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="group")
        message = SimpleNamespace(
            text="hello thread",
            caption=None,
            chat_id=42,
            message_thread_id=7,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        assert emitted[0]["message_thread_id"] == 7

    asyncio.run(_scenario())


def test_telegram_supergroup_topic_message_uses_topic_session_id() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="supergroup")
        message = SimpleNamespace(
            text="topic hello",
            caption=None,
            chat_id=-10042,
            message_thread_id=11,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        assert emitted[0][0] == "telegram:-10042:topic:11"

    asyncio.run(_scenario())


def test_telegram_private_thread_message_uses_thread_session_id() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="dm topic hello",
            caption=None,
            chat_id=42,
            message_thread_id=7,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        assert emitted[0][0] == "telegram:42:thread:7"
        assert emitted[0][3]["message_thread_id"] == 7

    asyncio.run(_scenario())


def test_telegram_media_only_message_is_forwarded_with_placeholder() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text=None,
            caption=None,
            photo=[SimpleNamespace(file_id="p1"), SimpleNamespace(file_id="p2")],
            voice=SimpleNamespace(file_id="v1"),
            audio=None,
            document=None,
            chat_id=42,
            from_user=user,
            message_id=11,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=101,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:42"
        assert user_id == "1"
        assert text == "[telegram media message: photo, voice]"
        assert metadata["media_present"] is True
        assert metadata["media_types"] == ["photo", "voice"]
        assert metadata["media_counts"] == {"photo": 1, "voice": 1}
        assert metadata["media_total_count"] == 2
        assert metadata["media_items"] == [
            {"type": "photo", "index": 1, "file_id": "p2", "variant_count": 2},
            {"type": "voice", "file_id": "v1"},
        ]

    asyncio.run(_scenario())


def test_telegram_media_group_messages_are_aggregated_into_one_turn() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        first = SimpleNamespace(
            text=None,
            caption="first caption",
            photo=[SimpleNamespace(file_id="p1")],
            voice=None,
            audio=None,
            document=None,
            video=None,
            animation=None,
            video_note=None,
            sticker=None,
            contact=None,
            location=None,
            media_group_id="album-1",
            chat_id=42,
            from_user=user,
            message_id=31,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        second = SimpleNamespace(
            text=None,
            caption="second caption",
            photo=[SimpleNamespace(file_id="p2")],
            voice=None,
            audio=None,
            document=None,
            video=None,
            animation=None,
            video_note=None,
            sticker=None,
            contact=None,
            location=None,
            media_group_id="album-1",
            chat_id=42,
            from_user=user,
            message_id=32,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        first_update = SimpleNamespace(
            update_id=500,
            message=first,
            edited_message=None,
            effective_message=first,
        )
        second_update = SimpleNamespace(
            update_id=501,
            message=second,
            edited_message=None,
            effective_message=second,
        )

        with patch.object(channel, "_start_typing_keepalive") as start_typing:
            with patch.object(
                channel, "_stop_typing_keepalive", AsyncMock()
            ) as stop_typing:
                with patch.object(
                    telegram_module.asyncio,
                    "sleep",
                    new=AsyncMock(return_value=None),
                ):
                    await channel._handle_update(first_update)
                    await channel._handle_update(second_update)
                    task = channel._media_group_tasks.get("42:album-1")
                    assert task is not None
                    await asyncio.wait_for(task, timeout=1.0)

        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:42"
        assert user_id == "1"
        assert text == (
            "[telegram media message: photo(2)]\n\nfirst caption\n\nsecond caption"
        )
        assert metadata["media_group_id"] == "album-1"
        assert metadata["message_ids"] == [31, 32]
        assert metadata["update_ids"] == [500, 501]
        assert metadata["media_group_message_count"] == 2
        assert metadata["media_counts"] == {"photo": 2}
        assert metadata["media_total_count"] == 2
        assert len(metadata["media_items"]) == 2
        start_typing.assert_called_once_with(chat_id="42", message_thread_id=None)
        stop_typing.assert_awaited_once_with(chat_id="42", message_thread_id=None)
        signals = channel.signals()
        assert signals["media_group_buffered_count"] == 2
        assert signals["media_group_flush_count"] == 1

    asyncio.run(_scenario())


def test_telegram_media_placeholder_covers_extended_media_types() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text=None,
            caption=None,
            video=SimpleNamespace(file_id="v1"),
            animation=SimpleNamespace(file_id="a1"),
            video_note=SimpleNamespace(file_id="vn1"),
            sticker=SimpleNamespace(file_id="s1"),
            contact=SimpleNamespace(phone_number="+15550001111"),
            location=SimpleNamespace(latitude=1.0, longitude=2.0),
            photo=None,
            voice=None,
            audio=None,
            document=None,
            chat_id=42,
            from_user=user,
            message_id=12,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=102,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        _, _, text, metadata = emitted[0]
        assert (
            text
            == "[telegram media message: animation, contact, location, sticker, video, video_note]"
        )
        assert metadata["media_types"] == [
            "animation",
            "contact",
            "location",
            "sticker",
            "video",
            "video_note",
        ]
        assert metadata["media_items"] == [
            {"type": "video", "file_id": "v1"},
            {"type": "animation", "file_id": "a1"},
            {"type": "video_note", "file_id": "vn1"},
            {"type": "sticker", "file_id": "s1"},
            {"type": "contact", "phone_number": "+15550001111"},
            {"type": "location", "latitude": 1.0, "longitude": 2.0},
        ]

    asyncio.run(_scenario())


def test_telegram_media_downloads_largest_photo_to_local_path(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        class FakeRemoteFile:
            def __init__(self) -> None:
                self.downloads: list[str] = []

            async def download_to_drive(self, path: str) -> None:
                self.downloads.append(path)
                Path(path).write_bytes(b"img")

        class FakeBot:
            def __init__(self) -> None:
                self.file_ids: list[str] = []
                self.remote = FakeRemoteFile()

            async def get_file(self, file_id: str):
                self.file_ids.append(file_id)
                return self.remote

        bot = FakeBot()
        channel.bot = bot
        channel._media_download_dir = lambda: tmp_path

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text=None,
            caption=None,
            photo=[SimpleNamespace(file_id="p1"), SimpleNamespace(file_id="p2")],
            voice=None,
            audio=None,
            document=None,
            chat_id=42,
            from_user=user,
            message_id=15,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=103,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert bot.file_ids == ["p2"]
        assert len(emitted) == 1
        assert "[telegram media message: photo]" in emitted[0][2]
        media_item = emitted[0][3]["media_items"][0]
        local_path = Path(media_item["local_path"])
        assert local_path.exists()
        assert local_path.read_bytes() == b"img"
        assert local_path.parent == tmp_path / "42"
        assert f"[photo saved: {local_path}]" in emitted[0][2]

    asyncio.run(_scenario())


def test_telegram_voice_media_transcription_enriches_text_and_metadata(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "media_download_dir": str(tmp_path / "media"),
                "transcription_api_key": "gkey",
                "transcription_language": "en",
                "transcribe_voice": True,
            },
            on_message=_on_message,
        )

        class FakeRemoteFile:
            async def download_to_drive(self, path: str) -> None:
                Path(path).write_bytes(b"voice")

        class FakeBot:
            def __init__(self) -> None:
                self.file_ids: list[str] = []

            async def get_file(self, file_id: str):
                self.file_ids.append(file_id)
                return FakeRemoteFile()

        bot = FakeBot()
        channel.bot = bot
        provider_instance = Mock()
        provider_instance.transcribe = AsyncMock(return_value="hello from voice note")

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text=None,
            caption=None,
            photo=None,
            voice=SimpleNamespace(file_id="v1"),
            audio=None,
            document=None,
            chat_id=42,
            from_user=user,
            message_id=16,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=104,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        with patch(
            "clawlite.providers.transcription.TranscriptionProvider",
            return_value=provider_instance,
        ) as provider_cls:
            await channel._handle_update(update)

        assert bot.file_ids == ["v1"]
        provider_cls.assert_called_once()
        provider_instance.transcribe.assert_awaited_once()
        assert len(emitted) == 1
        _, _, text, metadata = emitted[0]
        media_item = metadata["media_items"][0]
        assert media_item["file_id"] == "v1"
        assert media_item["transcription"] == "hello from voice note"
        assert media_item["transcription_language"] == "en"
        assert Path(media_item["local_path"]).parent == tmp_path / "media" / "42"
        assert text == (
            "[telegram media message: voice]\n\n"
            f"[voice saved: {media_item['local_path']}]\n"
            "[voice transcription: hello from voice note]"
        )
        signals = channel.signals()
        assert signals["media_download_count"] == 1
        assert signals["media_transcription_count"] == 1
        assert signals["media_transcription_error_count"] == 0

    asyncio.run(_scenario())


def test_telegram_document_media_download_enriches_text_with_saved_path(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "media_download_dir": str(tmp_path / "media")},
            on_message=_on_message,
        )

        class FakeRemoteFile:
            async def download_to_drive(self, path: str) -> None:
                Path(path).write_bytes(b"pdf")

        class FakeBot:
            def __init__(self) -> None:
                self.file_ids: list[str] = []

            async def get_file(self, file_id: str):
                self.file_ids.append(file_id)
                return FakeRemoteFile()

        bot = FakeBot()
        channel.bot = bot
        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text=None,
            caption=None,
            photo=None,
            voice=None,
            audio=None,
            document=SimpleNamespace(file_id="d1", file_name="brief.pdf", mime_type="application/pdf"),
            chat_id=42,
            from_user=user,
            message_id=17,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=105,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert bot.file_ids == ["d1"]
        assert len(emitted) == 1
        media_item = emitted[0][3]["media_items"][0]
        local_path = Path(media_item["local_path"])
        assert local_path.name.endswith(".pdf")
        assert emitted[0][2] == (
            "[telegram media message: document]\n\n"
            f"[document saved: {local_path}]"
        )

    asyncio.run(_scenario())


def test_telegram_callback_query_is_forwarded_and_acknowledged() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        class FakeBot:
            def __init__(self) -> None:
                self.acks: list[dict] = []

            async def answer_callback_query(self, **kwargs):
                self.acks.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        user = SimpleNamespace(id=7, username="alice")
        callback_message = SimpleNamespace(
            message_id=55,
            message_thread_id=4,
            chat=SimpleNamespace(id=42),
            chat_id=42,
        )
        callback_query = SimpleNamespace(
            id="cq-1",
            data="action:ok",
            chat_instance="inst-1",
            from_user=user,
            message=callback_message,
        )
        update = SimpleNamespace(
            update_id=100,
            callback_query=callback_query,
            message=None,
            edited_message=None,
            effective_message=None,
        )

        await channel._handle_update(update)

        assert len(bot.acks) == 1
        assert bot.acks[0]["callback_query_id"] == "cq-1"
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:42"
        assert user_id == "7"
        assert text == "action:ok"
        assert metadata["channel"] == "telegram"
        assert metadata["chat_id"] == "42"
        assert metadata["is_callback_query"] is True
        assert metadata["callback_query_id"] == "cq-1"
        assert metadata["callback_data"] == "action:ok"
        assert metadata["callback_chat_instance"] == "inst-1"
        assert metadata["message_id"] == 55
        assert metadata["message_thread_id"] == 4
        assert metadata["user_id"] == 7
        assert metadata["username"] == "alice"
        signals = channel.signals()
        assert signals["callback_query_received_count"] == 1
        assert signals["callback_query_ack_error_count"] == 0

    asyncio.run(_scenario())


def test_telegram_callback_query_supergroup_topic_uses_topic_session_id() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        class FakeBot:
            async def answer_callback_query(self, **kwargs):
                return kwargs

        channel.bot = FakeBot()
        callback_query = SimpleNamespace(
            id="cq-topic",
            data="action:topic",
            chat_instance="inst-topic",
            from_user=SimpleNamespace(id=7, username="alice"),
            message=SimpleNamespace(
                message_id=55,
                message_thread_id=4,
                chat=SimpleNamespace(id=-10077, type="supergroup"),
                chat_id=-10077,
            ),
        )
        update = SimpleNamespace(
            update_id=100,
            callback_query=callback_query,
            message=None,
            edited_message=None,
            effective_message=None,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        assert emitted[0][0] == "telegram:-10077:topic:4"

    asyncio.run(_scenario())


def test_telegram_message_reaction_supergroup_topic_uses_topic_session_id() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "reaction_notifications": "all"},
            on_message=_on_message,
        )
        update = SimpleNamespace(
            update_id=110,
            callback_query=None,
            message_reaction=SimpleNamespace(
                chat=SimpleNamespace(id=-10011, type="supergroup"),
                message_thread_id=7,
                message_id=99,
                user=SimpleNamespace(id=9, username="guest", is_bot=False),
                old_reaction=[],
                new_reaction=[SimpleNamespace(emoji="🔥")],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        await channel._handle_update(update)

        assert len(emitted) == 1
        assert emitted[0][0] == "telegram:-10011:topic:7"

    asyncio.run(_scenario())


def test_telegram_callback_query_blocked_by_allowlist_does_not_emit() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "allowFrom": ["123"]},
            on_message=_on_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.acks: list[dict] = []

            async def answer_callback_query(self, **kwargs):
                self.acks.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        callback_query = SimpleNamespace(
            id="cq-2",
            data="action:block",
            chat_instance="inst-2",
            from_user=SimpleNamespace(id=999, username="guest"),
            message=SimpleNamespace(
                message_id=56,
                chat=SimpleNamespace(id=42),
                chat_id=42,
            ),
        )
        update = SimpleNamespace(
            update_id=101,
            callback_query=callback_query,
            message=None,
            edited_message=None,
            effective_message=None,
        )

        await channel._handle_update(update)

        assert emitted == []
        assert len(bot.acks) == 1
        signals = channel.signals()
        assert signals["callback_query_received_count"] == 1
        assert signals["callback_query_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_callback_sign_payload_uses_random_nonce_per_signature() -> None:
    channel = TelegramChannel(
        config={
            "token": "x:token",
            "callback_signing_enabled": True,
            "callback_signing_secret": "secret-1",
        }
    )

    signed_a = channel._callback_sign_payload("approve:1")
    signed_b = channel._callback_sign_payload("approve:1")

    assert signed_a != signed_b
    _, nonce_a, encoded_a, signature_a = signed_a.split(".", 3)
    _, nonce_b, encoded_b, signature_b = signed_b.split(".", 3)
    assert encoded_a == encoded_b
    assert nonce_a != nonce_b
    assert signature_a != signature_b


def test_telegram_callback_verify_payload_accepts_valid_signed_data() -> None:
    channel = TelegramChannel(
        config={
            "token": "x:token",
            "callback_signing_enabled": True,
            "callback_signing_secret": "secret-1",
        }
    )

    signed = channel._callback_sign_payload("approve:1")

    ok, decoded, was_signed = channel._callback_verify_payload(signed)

    assert ok is True
    assert decoded == "approve:1"
    assert was_signed is True


def test_telegram_callback_verify_payload_rejects_tampered_payload() -> None:
    channel = TelegramChannel(
        config={
            "token": "x:token",
            "callback_signing_enabled": True,
            "callback_signing_secret": "secret-1",
        }
    )

    signed = channel._callback_sign_payload("approve:1")
    _, nonce, encoded_data, signature = signed.split(".", 3)
    tampered_signature = signature[:-1] + ("A" if signature[-1] != "A" else "B")
    tampered = f"s1.{nonce}.{encoded_data}.{tampered_signature}"

    ok, decoded, was_signed = channel._callback_verify_payload(tampered)

    assert ok is False
    assert decoded == ""
    assert was_signed is True


def test_telegram_callback_signing_accepts_valid_signed_callback() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "callback_signing_enabled": True,
                "callback_signing_secret": "secret-1",
            },
            on_message=_on_message,
        )

        class FakeBot:
            async def answer_callback_query(self, **kwargs):
                return kwargs

        channel.bot = FakeBot()
        signed = channel._callback_sign_payload("approve:1")
        callback_query = SimpleNamespace(
            id="cq-sign-ok",
            data=signed,
            chat_instance="inst-sign",
            from_user=SimpleNamespace(id=7, username="alice"),
            message=SimpleNamespace(
                message_id=55, chat=SimpleNamespace(id=42, type="group"), chat_id=42
            ),
        )

        await channel._handle_update(
            SimpleNamespace(
                update_id=100,
                callback_query=callback_query,
                message=None,
                edited_message=None,
                effective_message=None,
            )
        )

        assert len(emitted) == 1
        assert emitted[0][2] == "approve:1"
        assert emitted[0][3]["callback_data"] == "approve:1"
        assert emitted[0][3]["callback_signed"] is True
        signals = channel.signals()
        assert signals["callback_query_signature_accepted_count"] == 1
        assert signals["callback_query_signature_blocked_count"] == 0

    asyncio.run(_scenario())


def test_telegram_callback_signing_blocks_tampered_signed_callback() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "callback_signing_enabled": True,
                "callback_signing_secret": "secret-1",
            },
            on_message=_on_message,
        )

        class FakeBot:
            async def answer_callback_query(self, **kwargs):
                return kwargs

        channel.bot = FakeBot()
        signed = channel._callback_sign_payload("approve:1")
        tampered = signed[:-1] + ("A" if signed[-1] != "A" else "B")
        callback_query = SimpleNamespace(
            id="cq-sign-bad",
            data=tampered,
            chat_instance="inst-sign",
            from_user=SimpleNamespace(id=7, username="alice"),
            message=SimpleNamespace(
                message_id=55, chat=SimpleNamespace(id=42, type="group"), chat_id=42
            ),
        )

        await channel._handle_update(
            SimpleNamespace(
                update_id=100,
                callback_query=callback_query,
                message=None,
                edited_message=None,
                effective_message=None,
            )
        )

        assert emitted == []
        signals = channel.signals()
        assert signals["callback_query_signature_blocked_count"] == 1
        assert signals["callback_query_blocked_count"] >= 1

    asyncio.run(_scenario())


def test_telegram_callback_require_signed_controls_unsigned_behavior() -> None:
    async def _scenario() -> None:
        allow_emitted: list[tuple[str, str, str, dict]] = []
        block_emitted: list[tuple[str, str, str, dict]] = []

        async def _allow_handler(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            allow_emitted.append((session_id, user_id, text, metadata))

        async def _block_handler(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            block_emitted.append((session_id, user_id, text, metadata))

        allow_channel = TelegramChannel(
            config={"token": "x:token", "callback_require_signed": False},
            on_message=_allow_handler,
        )
        block_channel = TelegramChannel(
            config={"token": "x:token", "callback_require_signed": True},
            on_message=_block_handler,
        )

        class FakeBot:
            async def answer_callback_query(self, **kwargs):
                return kwargs

        allow_channel.bot = FakeBot()
        block_channel.bot = FakeBot()

        callback_query = SimpleNamespace(
            id="cq-unsigned",
            data="plain:callback",
            chat_instance="inst-unsigned",
            from_user=SimpleNamespace(id=7, username="alice"),
            message=SimpleNamespace(
                message_id=55, chat=SimpleNamespace(id=42, type="group"), chat_id=42
            ),
        )
        update = SimpleNamespace(
            update_id=100,
            callback_query=callback_query,
            message=None,
            edited_message=None,
            effective_message=None,
        )

        await allow_channel._handle_update(update)
        await block_channel._handle_update(update)

        assert len(allow_emitted) == 1
        assert block_emitted == []
        assert allow_channel.signals()["callback_query_unsigned_allowed_count"] == 1
        assert block_channel.signals()["callback_query_signature_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_update_dedupe_state_persists_across_restarts(tmp_path: Path) -> None:
    async def _scenario() -> None:
        dedupe_path = tmp_path / "telegram-dedupe.json"
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
                "update_dedupe_limit": 8,
            }
        )

        assert (
            channel._remember_update_dedupe_key("update:101", source="polling") is True
        )
        assert (
            channel._remember_update_dedupe_key("update:102", source="polling") is True
        )
        await channel._persist_update_dedupe_state()

        reloaded = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
                "update_dedupe_limit": 8,
            }
        )
        assert (
            reloaded._remember_update_dedupe_key("update:101", source="polling")
            is False
        )
        assert (
            reloaded._remember_update_dedupe_key("update:103", source="polling") is True
        )

    asyncio.run(_scenario())


def test_telegram_stop_flushes_pending_dedupe_state_before_restart(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        dedupe_path = tmp_path / "telegram-dedupe.json"
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
                "update_dedupe_limit": 8,
            }
        )

        channel._running = True
        assert (
            channel._remember_update_dedupe_key("update:301", source="polling") is True
        )
        assert channel._dedupe_persist_task is not None
        await channel.stop()

        reloaded = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
                "update_dedupe_limit": 8,
            }
        )
        assert (
            reloaded._remember_update_dedupe_key("update:301", source="polling")
            is False
        )

    asyncio.run(_scenario())


def test_telegram_update_dedupe_state_uses_durable_atomic_write(tmp_path: Path) -> None:
    async def _scenario() -> None:
        dedupe_path = tmp_path / "telegram-dedupe.json"
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
            }
        )
        channel._remember_update_dedupe_key("update:201", source="polling")

        fsync_fds: list[int] = []
        real_fsync = telegram_module.os.fsync

        def _tracking_fsync(fd: int) -> None:
            fsync_fds.append(fd)
            real_fsync(fd)

        with patch("clawlite.channels.telegram.os.fsync", side_effect=_tracking_fsync):
            await channel._persist_update_dedupe_state()

        persisted = json.loads(dedupe_path.read_text(encoding="utf-8"))
        assert persisted["keys"] == ["update:201"]
        assert len(fsync_fds) >= 1
        assert not list(tmp_path.glob("telegram-dedupe.json.tmp*"))

    asyncio.run(_scenario())


def test_telegram_markdown_code_tokens_do_not_collide_with_user_text() -> None:
    markdown = (
        "prefix \\x00TG_CB_deadbeefdeadbeef\\x00 and \\x00TG_IC_deadbeefdeadbeef\\x00\n\n"
        '```py\nif x < y and y > z:\n    print("ok")\n```\n'
        "inline `a < b` tail"
    )

    rendered = markdown_to_telegram_html(markdown)

    assert (
        '<pre><code>if x &lt; y and y &gt; z:\n    print("ok")\n</code></pre>'
        in rendered
    )
    assert "<code>a &lt; b</code>" in rendered
    assert "\\x00TG_CB_deadbeefdeadbeef\\x00" in rendered
    assert "\\x00TG_IC_deadbeefdeadbeef\\x00" in rendered


def test_telegram_markdown_expands_inline_bullets_into_readable_lines() -> None:
    rendered = markdown_to_telegram_html(
        "O que eu faço melhor: - responder - editar arquivos - rodar testes"
    )

    assert "O que eu faço melhor:\n" in rendered
    assert "&#8226; responder" in rendered
    assert "&#8226; editar arquivos" in rendered
    assert "&#8226; rodar testes" in rendered


def test_telegram_markdown_expands_inline_numbered_list_into_readable_lines() -> None:
    rendered = markdown_to_telegram_html(
        "Passos: 1. abrir o arquivo 2. editar o trecho 3. rodar os testes"
    )

    assert "Passos:\n" in rendered
    assert "1. abrir o arquivo" in rendered
    assert "2. editar o trecho" in rendered
    assert "3. rodar os testes" in rendered


def test_telegram_markdown_formats_heading_and_table_into_clean_html() -> None:
    rendered = markdown_to_telegram_html(
        "# Resumo\n\n| Coluna | Valor |\n| --- | --- |\n| Nome | ClawLite |\n| Canal | Telegram |"
    )

    assert "<b>Resumo</b>" in rendered
    assert "<pre><code>" in rendered
    assert "Coluna  Valor" in rendered
    assert "Nome    ClawLite" in rendered


def test_telegram_markdown_strips_replacement_and_control_chars() -> None:
    rendered = markdown_to_telegram_html("Oi!\ufffd\ufffd\n\x00# Titulo")

    assert "\ufffd" not in rendered
    assert "\x00" not in rendered
    assert "<b>Titulo</b>" in rendered


def test_telegram_module_import_does_not_call_setup_logging() -> None:
    source = Path(telegram_module.__file__).read_text(encoding="utf-8")
    assert "from clawlite.utils.logging import setup_logging" not in source
    assert "setup_logging()" not in source


def test_telegram_send_markdown_falls_back_to_plain_text() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FormattingError(RuntimeError):
            status_code = 400

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("parse_mode") == "HTML":
                    raise FormattingError("can't parse entities")

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(target="42", text="**hello**")

        assert out == "telegram:sent:1"
        assert len(bot.calls) == 2
        assert bot.calls[0]["parse_mode"] == "HTML"
        assert bot.calls[1]["text"] == "**hello**"
        assert bot.calls[1]["parse_mode"] is None

    asyncio.run(_scenario())


def test_telegram_send_supports_raw_html_parse_mode_from_metadata() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(message_id=91)

        bot = FakeBot()
        channel.bot = bot

        html_text = "<b>hello</b> <i>team</i> <code>x=1</code>"
        out = await channel.send(
            target="42", text=html_text, metadata={"telegram_parse_mode": "html"}
        )

        assert out == "telegram:sent:1"
        assert len(bot.calls) == 1
        assert bot.calls[0]["text"] == html_text
        assert bot.calls[0]["parse_mode"] == "HTML"

    asyncio.run(_scenario())


def test_telegram_send_supports_inline_keyboard_from_metadata() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot
        metadata = {
            "telegram_inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": "approve:1"},
                    {"text": "Open", "url": "https://example.com"},
                ]
            ]
        }

        out = await channel.send(target="42", text="choose", metadata=metadata)

        assert out == "telegram:sent:1"
        assert len(bot.calls) == 1
        assert "reply_markup" in bot.calls[0]
        reply_markup = bot.calls[0]["reply_markup"]
        if isinstance(reply_markup, dict):
            assert reply_markup["inline_keyboard"][0][0]["text"] == "Approve"
            assert reply_markup["inline_keyboard"][0][0]["callback_data"] == "approve:1"
            assert reply_markup["inline_keyboard"][0][1]["text"] == "Open"
            assert reply_markup["inline_keyboard"][0][1]["url"] == "https://example.com"
        else:
            button_a = reply_markup.inline_keyboard[0][0]
            button_b = reply_markup.inline_keyboard[0][1]
            assert button_a.text == "Approve"
            assert button_a.callback_data == "approve:1"
            assert button_b.text == "Open"
            assert button_b.url == "https://example.com"

    asyncio.run(_scenario())


def test_telegram_action_edit_dispatches_and_returns_marker() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def edit_message_text(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(
            target="42",
            text="**patched**",
            metadata={"_telegram_action": "edit", "_telegram_action_message_id": 77},
        )

        assert out == "telegram:edited:77"
        assert len(bot.calls) == 1
        assert bot.calls[0]["chat_id"] == "42"
        assert bot.calls[0]["message_id"] == 77
        assert channel.signals()["action_edit_count"] == 1

    asyncio.run(_scenario())


def test_telegram_action_delete_dispatches_and_returns_marker() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def delete_message(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(
            target="42",
            text="ignored",
            metadata={"_telegram_action": "delete", "_telegram_action_message_id": 88},
        )

        assert out == "telegram:deleted:88"
        assert len(bot.calls) == 1
        assert bot.calls[0]["chat_id"] == "42"
        assert bot.calls[0]["message_id"] == 88
        assert channel.signals()["action_delete_count"] == 1

    asyncio.run(_scenario())


def test_telegram_action_react_dispatches_and_returns_marker() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def set_message_reaction(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(
            target="42",
            text="ignored",
            metadata={
                "_telegram_action": "react",
                "_telegram_action_message_id": 99,
                "_telegram_action_emoji": ":fire:",
            },
        )

        assert out == "telegram:reacted:99"
        assert len(bot.calls) == 1
        assert bot.calls[0]["chat_id"] == "42"
        assert bot.calls[0]["message_id"] == 99
        assert bot.calls[0]["reaction"] == [{"type": "emoji", "emoji": ":fire:"}]
        assert channel.signals()["action_react_count"] == 1

    asyncio.run(_scenario())


def test_telegram_action_create_topic_dispatches_and_returns_marker() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def create_forum_topic(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(message_thread_id=123)

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(
            target="-10042",
            text="ignored",
            metadata={
                "_telegram_action": "create_topic",
                "_telegram_action_topic_name": "Ops",
                "_telegram_action_topic_icon_color": 7322096,
            },
        )

        assert out == "telegram:topic_created:123"
        assert len(bot.calls) == 1
        assert bot.calls[0]["chat_id"] == "-10042"
        assert bot.calls[0]["name"] == "Ops"
        assert bot.calls[0]["icon_color"] == 7322096
        assert channel.signals()["action_create_topic_count"] == 1

    asyncio.run(_scenario())


def test_telegram_send_retries_transient_failures() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_retry_attempts": 3,
                "send_backoff_base_s": 0.01,
                "send_backoff_max_s": 0.01,
                "send_backoff_jitter": 0.0,
            }
        )

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def send_message(self, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise TimeoutError("timed out")
                return kwargs

        bot = FakeBot()
        channel.bot = bot

        with patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()):
            out = await channel.send(target="42", text="hello")

        assert out == "telegram:sent:1"
        assert bot.calls == 3

    asyncio.run(_scenario())


def test_telegram_send_retries_with_retry_after_delay() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_retry_attempts": 3,
                "send_backoff_base_s": 0.01,
                "send_backoff_max_s": 0.01,
                "send_backoff_jitter": 0.0,
            }
        )

        class RetryAfterError(RuntimeError):
            status_code = 429

            def __init__(self, retry_after: float) -> None:
                super().__init__("too many requests")
                self.retry_after = retry_after

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def send_message(self, **kwargs):
                del kwargs
                self.calls += 1
                if self.calls == 1:
                    raise RetryAfterError(2.5)
                return True

        bot = FakeBot()
        channel.bot = bot

        sleep_mock = AsyncMock()
        with patch("clawlite.channels.telegram.asyncio.sleep", new=sleep_mock):
            out = await channel.send(target="42", text="hello")

        assert out == "telegram:sent:1"
        assert bot.calls == 2
        assert sleep_mock.await_count == 1
        assert sleep_mock.await_args.args == (2.5,)

    asyncio.run(_scenario())


def test_telegram_send_supports_message_thread_id_from_metadata() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(
            target="42", text="hello", metadata={"message_thread_id": 13}
        )

        assert out == "telegram:sent:1"
        assert bot.calls[0]["chat_id"] == "42"
        assert bot.calls[0]["message_thread_id"] == 13

    asyncio.run(_scenario())


def test_telegram_send_supports_message_thread_id_from_target() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(target="42:9", text="hello")

        assert out == "telegram:sent:1"
        assert bot.calls[0]["chat_id"] == "42"
        assert bot.calls[0]["message_thread_id"] == 9

    asyncio.run(_scenario())


def test_telegram_send_accepts_topic_style_session_target() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(target="telegram:-10042:topic:9", text="hello")

        assert out == "telegram:sent:1"
        assert bot.calls[0]["chat_id"] == "-10042"
        assert bot.calls[0]["message_thread_id"] == 9

    asyncio.run(_scenario())


def test_telegram_send_accepts_private_thread_style_session_target() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(target="telegram:42:thread:7", text="hello")

        assert out == "telegram:sent:1"
        assert bot.calls[0]["chat_id"] == "42"
        assert bot.calls[0]["message_thread_id"] == 7

    asyncio.run(_scenario())


def test_telegram_send_retries_without_thread_when_dm_thread_is_not_found() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class ThreadNotFoundError(RuntimeError):
            status_code = 400

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    raise ThreadNotFoundError(
                        "400: Bad Request: message thread not found"
                    )
                return SimpleNamespace(message_id=101)

        bot = FakeBot()
        channel.bot = bot
        metadata: dict[str, object] = {"message_thread_id": 9}

        out = await channel.send(target="42", text="hello", metadata=metadata)

        assert out == "telegram:sent:1"
        assert len(bot.calls) == 2
        assert bot.calls[0]["message_thread_id"] == 9
        assert "message_thread_id" not in bot.calls[1]
        receipt = metadata.get("_delivery_receipt")
        assert isinstance(receipt, dict)
        assert "message_thread_id" not in receipt
        assert channel.signals()["send_retry_count"] == 0

    asyncio.run(_scenario())


def test_telegram_send_omits_general_topic_thread_id_for_group_target() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(message_id=201)

        bot = FakeBot()
        channel.bot = bot
        metadata: dict[str, object] = {"message_thread_id": 1}

        out = await channel.send(target="-100123", text="hello", metadata=metadata)

        assert out == "telegram:sent:1"
        assert len(bot.calls) == 1
        assert bot.calls[0]["chat_id"] == "-100123"
        assert "message_thread_id" not in bot.calls[0]
        receipt = metadata.get("_delivery_receipt")
        assert isinstance(receipt, dict)
        assert "message_thread_id" not in receipt

    asyncio.run(_scenario())


def test_telegram_send_populates_delivery_receipt_for_chunked_send() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []
                self.message_id = 100

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                self.message_id += 1
                return SimpleNamespace(message_id=self.message_id)

        bot = FakeBot()
        channel.bot = bot
        text = ("A" * 4000) + ("B" * 20)
        metadata: dict[str, object] = {"message_thread_id": 9}

        out = await channel.send(target="42", text=text, metadata=metadata)

        assert out == "telegram:sent:2"
        receipt = metadata.get("_delivery_receipt")
        assert isinstance(receipt, dict)
        assert receipt["channel"] == "telegram"
        assert receipt["chat_id"] == "42"
        assert receipt["message_thread_id"] == 9
        assert receipt["chunks"] == 2
        assert receipt["message_ids"] == [101, 102]
        assert receipt["last_message_id"] == 102

    asyncio.run(_scenario())


def test_telegram_send_supports_media_attachments_and_delivery_receipt() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.photo_calls: list[dict] = []
                self.document_calls: list[dict] = []

            async def send_photo(self, **kwargs):
                self.photo_calls.append(kwargs)
                return SimpleNamespace(message_id=101)

            async def send_document(self, **kwargs):
                self.document_calls.append(kwargs)
                return SimpleNamespace(message_id=102)

        bot = FakeBot()
        channel.bot = bot
        metadata: dict[str, object] = {
            "message_thread_id": 7,
            "media": [
                {"type": "photo", "file_id": "photo-1"},
                {"type": "document", "file_id": "doc-1"},
            ],
        }

        out = await channel.send(target="42", text="**hello**", metadata=metadata)

        assert out == "telegram:sent:2"
        assert len(bot.photo_calls) == 1
        assert bot.photo_calls[0]["chat_id"] == "42"
        assert bot.photo_calls[0]["photo"] == "photo-1"
        assert bot.photo_calls[0]["caption"] == markdown_to_telegram_html("**hello**")
        assert bot.photo_calls[0]["parse_mode"] == "HTML"
        assert bot.photo_calls[0]["message_thread_id"] == 7
        assert len(bot.document_calls) == 1
        assert bot.document_calls[0]["chat_id"] == "42"
        assert bot.document_calls[0]["document"] == "doc-1"
        assert bot.document_calls[0]["message_thread_id"] == 7
        assert "caption" not in bot.document_calls[0]
        receipt = metadata.get("_delivery_receipt")
        assert isinstance(receipt, dict)
        assert receipt["chunks"] == 2
        assert receipt["message_ids"] == [101, 102]
        assert receipt["media_count"] == 2
        assert receipt["media_types"] == ["photo", "document"]

    asyncio.run(_scenario())


def test_telegram_send_assigns_caption_to_first_caption_capable_media_item() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.sticker_calls: list[dict] = []
                self.photo_calls: list[dict] = []
                self.message_calls: list[dict] = []

            async def send_sticker(self, **kwargs):
                self.sticker_calls.append(kwargs)
                return SimpleNamespace(message_id=301)

            async def send_photo(self, **kwargs):
                self.photo_calls.append(kwargs)
                return SimpleNamespace(message_id=302)

            async def send_message(self, **kwargs):
                self.message_calls.append(kwargs)
                return SimpleNamespace(message_id=303)

        bot = FakeBot()
        channel.bot = bot
        metadata: dict[str, object] = {
            "media": [
                {"type": "sticker", "file_id": "sticker-1"},
                {"type": "photo", "file_id": "photo-1"},
            ],
        }

        out = await channel.send(target="42", text="**hello**", metadata=metadata)

        assert out == "telegram:sent:2"
        assert len(bot.sticker_calls) == 1
        assert "caption" not in bot.sticker_calls[0]
        assert len(bot.photo_calls) == 1
        assert bot.photo_calls[0]["caption"] == markdown_to_telegram_html("**hello**")
        assert bot.photo_calls[0]["parse_mode"] == "HTML"
        assert bot.message_calls == []

    asyncio.run(_scenario())


def test_telegram_send_falls_back_to_follow_up_text_when_media_has_no_caption_support() -> (
    None
):
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.video_note_calls: list[dict] = []
                self.message_calls: list[dict] = []

            async def send_video_note(self, **kwargs):
                self.video_note_calls.append(kwargs)
                return SimpleNamespace(message_id=401)

            async def send_message(self, **kwargs):
                self.message_calls.append(kwargs)
                return SimpleNamespace(message_id=402)

        bot = FakeBot()
        channel.bot = bot
        metadata: dict[str, object] = {
            "media": [{"type": "video_note", "file_id": "video-note-1"}],
        }

        out = await channel.send(target="42", text="hello", metadata=metadata)

        assert out == "telegram:sent:2"
        assert len(bot.video_note_calls) == 1
        assert "caption" not in bot.video_note_calls[0]
        assert len(bot.message_calls) == 1
        assert bot.message_calls[0]["text"] == "hello"
        assert (
            "parse_mode" not in bot.message_calls[0]
            or bot.message_calls[0]["parse_mode"] == "HTML"
        )

    asyncio.run(_scenario())


def test_telegram_send_places_reply_markup_on_follow_up_text_when_media_caption_is_too_long() -> (
    None
):
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.photo_calls: list[dict] = []
                self.message_calls: list[dict] = []

            async def send_photo(self, **kwargs):
                self.photo_calls.append(kwargs)
                return SimpleNamespace(message_id=201)

            async def send_message(self, **kwargs):
                self.message_calls.append(kwargs)
                return SimpleNamespace(message_id=202)

        bot = FakeBot()
        channel.bot = bot
        long_text = "A" * 1030
        metadata: dict[str, object] = {
            "media": [{"type": "photo", "file_id": "photo-1"}],
            "telegram_inline_keyboard": [
                [{"text": "Open", "url": "https://example.com"}]
            ],
        }

        out = await channel.send(target="42", text=long_text, metadata=metadata)

        assert out == "telegram:sent:2"
        assert len(bot.photo_calls) == 1
        assert bot.photo_calls[0]["photo"] == "photo-1"
        assert "caption" not in bot.photo_calls[0]
        assert "reply_markup" not in bot.photo_calls[0]
        assert len(bot.message_calls) == 1
        assert bot.message_calls[0]["text"] == long_text
        assert "reply_markup" in bot.message_calls[0]
        receipt = metadata.get("_delivery_receipt")
        assert isinstance(receipt, dict)
        assert receipt["chunks"] == 2
        assert receipt["message_ids"] == [201, 202]

    asyncio.run(_scenario())


def test_telegram_send_media_caption_supports_raw_html_parse_mode_from_metadata() -> (
    None
):
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.photo_calls: list[dict] = []

            async def send_photo(self, **kwargs):
                self.photo_calls.append(kwargs)
                return SimpleNamespace(message_id=301)

        bot = FakeBot()
        channel.bot = bot
        html_text = "<b>hello</b> <i>team</i>"
        metadata: dict[str, object] = {
            "telegram_parse_mode": "html",
            "media": [{"type": "photo", "file_id": "photo-1"}],
        }

        out = await channel.send(target="42", text=html_text, metadata=metadata)

        assert out == "telegram:sent:1"
        assert len(bot.photo_calls) == 1
        assert bot.photo_calls[0]["caption"] == html_text
        assert bot.photo_calls[0]["parse_mode"] == "HTML"

    asyncio.run(_scenario())


def test_telegram_send_retries_without_thread_kwarg_on_old_library() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                if "message_thread_id" in kwargs:
                    raise TypeError(
                        "got an unexpected keyword argument 'message_thread_id'"
                    )
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(target="42:5", text="hello")

        assert out == "telegram:sent:1"
        assert len(bot.calls) == 2
        assert "message_thread_id" in bot.calls[0]
        assert "message_thread_id" not in bot.calls[1]

    asyncio.run(_scenario())


def test_telegram_send_media_retries_without_thread_when_dm_thread_is_not_found() -> (
    None
):
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class ThreadNotFoundError(RuntimeError):
            status_code = 400

        class FakeBot:
            def __init__(self) -> None:
                self.photo_calls: list[dict] = []

            async def send_photo(self, **kwargs):
                self.photo_calls.append(kwargs)
                if len(self.photo_calls) == 1:
                    raise ThreadNotFoundError(
                        "400: Bad Request: message thread not found"
                    )
                return SimpleNamespace(message_id=301)

        bot = FakeBot()
        channel.bot = bot
        metadata: dict[str, object] = {
            "message_thread_id": 7,
            "media": [{"type": "photo", "file_id": "photo-1"}],
        }

        out = await channel.send(target="42", text="hello", metadata=metadata)

        assert out == "telegram:sent:1"
        assert len(bot.photo_calls) == 2
        assert bot.photo_calls[0]["message_thread_id"] == 7
        assert "message_thread_id" not in bot.photo_calls[1]
        receipt = metadata.get("_delivery_receipt")
        assert isinstance(receipt, dict)
        assert "message_thread_id" not in receipt
        assert channel.signals()["send_retry_count"] == 0

    asyncio.run(_scenario())


def test_telegram_send_auth_circuit_breaker_opens() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_circuit_failure_threshold": 1,
                "send_circuit_cooldown_s": 60,
            }
        )

        class AuthError(RuntimeError):
            status_code = 401

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def send_message(self, **kwargs):
                self.calls += 1
                raise AuthError("unauthorized")

        bot = FakeBot()
        channel.bot = bot

        try:
            await channel.send(target="42", text="hello")
            raise AssertionError("expected auth error")
        except AuthError:
            pass

        try:
            await channel.send(target="42", text="hello")
            raise AssertionError("expected open circuit")
        except TelegramCircuitOpenError:
            pass

        assert bot.calls == 1

    asyncio.run(_scenario())


def test_telegram_send_auth_circuit_breaker_cooldown_then_recover() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_circuit_failure_threshold": 1,
                "send_circuit_cooldown_s": 0.05,
            }
        )

        class AuthError(RuntimeError):
            status_code = 401

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def send_message(self, **kwargs):
                del kwargs
                self.calls += 1
                if self.calls == 1:
                    raise AuthError("unauthorized")
                return True

        bot = FakeBot()
        channel.bot = bot

        try:
            await channel.send(target="42", text="hello")
            raise AssertionError("expected auth error")
        except AuthError:
            pass

        try:
            await channel.send(target="42", text="hello")
            raise AssertionError("expected open circuit")
        except TelegramCircuitOpenError:
            pass

        channel._send_auth_breaker._open_until_monotonic = 0.0
        out = await channel.send(target="42", text="hello")

        assert out == "telegram:sent:1"
        assert bot.calls == 2
        signals = channel.signals()
        assert signals["send_auth_breaker_open_count"] >= 1
        assert signals["send_auth_breaker_open"] is False

    asyncio.run(_scenario())


def test_telegram_offset_commits_after_successful_processing(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        offset_path = tmp_path / "offset.json"
        _bind_offset_path(channel, offset_path)

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                self.calls += 1
                if self.calls == 1:
                    return [update]
                channel._running = False
                return []

            async def send_message(self, **kwargs):
                return kwargs

        channel.bot = FakeBot()
        channel._running = True
        await channel._poll_loop()

        assert emitted == ["hello"]
        assert channel._offset == 101
        persisted = json.loads(offset_path.read_text(encoding="utf-8"))
        assert persisted["safe_update_id"] == 100
        assert persisted["next_offset"] == 101
        assert persisted["pending_update_ids"] == []

    asyncio.run(_scenario())


def test_telegram_offset_not_committed_when_processing_fails(tmp_path: Path) -> None:
    async def _scenario() -> None:
        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, text, metadata
            channel._running = False
            raise RuntimeError("boom")

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        offset_path = tmp_path / "offset.json"
        _bind_offset_path(channel, offset_path)

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        class FakeBot:
            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                return [update]

            async def send_message(self, **kwargs):
                return kwargs

        channel.bot = FakeBot()
        channel._running = True
        with patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()):
            await channel._poll_loop()

        assert channel._offset == 0
        persisted = json.loads(offset_path.read_text(encoding="utf-8"))
        assert persisted["safe_update_id"] is None
        assert persisted["pending_update_ids"] == [100]

    asyncio.run(_scenario())


def test_telegram_load_offset_accepts_legacy_payload(tmp_path: Path) -> None:
    channel = TelegramChannel(config={"token": "x:token"})
    offset_path = tmp_path / "offset.json"
    offset_path.write_text(json.dumps({"offset": 77}), encoding="utf-8")
    channel._offset_store.path = offset_path

    loaded = channel._load_offset()

    assert loaded == 77
    assert channel.signals()["offset_load_error_count"] == 0


def test_telegram_save_offset_writes_safe_watermark_payload(
    tmp_path: Path,
) -> None:
    channel = TelegramChannel(config={"token": "x:token"})
    offset_path = tmp_path / "offset.json"
    channel._offset_store.path = offset_path
    channel._offset = 123

    fsync_fds: list[int] = []
    real_fsync = telegram_module.os.fsync

    def _tracking_fsync(fd: int) -> None:
        fsync_fds.append(fd)
        real_fsync(fd)

    with patch("clawlite.channels.telegram.os.fsync", side_effect=_tracking_fsync):
        channel._save_offset()

    persisted = json.loads(offset_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 3
    assert persisted["safe_update_id"] == 122
    assert persisted["highest_completed_update_id"] == 122
    assert persisted["next_offset"] == 123
    assert persisted["pending_update_ids"] == []
    assert isinstance(persisted["updated_at"], str) and persisted["updated_at"]
    assert (
        persisted["token_fingerprint"]
        == hashlib.sha256("x:token".encode("utf-8")).hexdigest()[:16]
    )
    assert len(fsync_fds) >= 1
    assert not list(tmp_path.glob("offset.json.tmp*"))
    assert channel.signals()["offset_persist_error_count"] == 0


def test_telegram_offset_store_keeps_watermark_below_pending_until_gap_closes(
    tmp_path: Path,
) -> None:
    store = TelegramOffsetStore(token="x:token", state_path=tmp_path / "offset.json")

    store.force_commit(100)
    store.begin(101)
    store.begin(102)
    partial = store.mark_completed(102, tracked_pending=True)

    assert partial.safe_update_id == 100
    assert partial.next_offset == 101
    assert partial.pending_update_ids == (101,)
    assert partial.completed_update_ids == (102,)

    complete = store.mark_completed(101, tracked_pending=True)

    assert complete.safe_update_id == 102
    assert complete.next_offset == 103
    assert complete.pending_update_ids == ()
    assert complete.completed_update_ids == ()


def test_telegram_offset_state_path_config_persists_to_custom_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "telegram-offset.json"
    channel = TelegramChannel(
        config={
            "token": "x:token",
            "offset_state_path": str(path),
        }
    )

    assert channel._offset_path() == path

    channel._force_commit_offset_update(55)

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["safe_update_id"] == 55
    assert persisted["next_offset"] == 56
    assert channel._offset == 56


def test_telegram_polling_transient_failure_recovers_and_processes_update(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)
            channel._running = False

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "reconnect_initial_s": 0.01,
                "reconnect_max_s": 0.01,
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        _bind_offset_path(channel, tmp_path / "offset.json")

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        class FirstBot:
            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                raise TimeoutError("timed out")

        class SecondBot:
            def __init__(self) -> None:
                self.calls = 0

            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                self.calls += 1
                if self.calls == 1:
                    return [update]
                channel._running = False
                return []

        bot_factory = Mock(side_effect=[FirstBot(), SecondBot()])
        channel._running = True
        fake_module = SimpleNamespace(Bot=bot_factory)
        with (
            patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()),
            patch.dict(sys.modules, {"telegram": fake_module}),
        ):
            await channel._poll_loop()

        assert emitted == ["hello"]
        assert channel._offset == 101
        assert channel.signals()["reconnect_count"] >= 1

    asyncio.run(_scenario())


def test_telegram_polling_soak_recovery_reconnects_then_stabilizes(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "reconnect_initial_s": 0.01,
                "reconnect_max_s": 0.02,
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        _bind_offset_path(channel, tmp_path / "offset.json")

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="stabilized",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        class FailingBot:
            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                raise TimeoutError("timed out")

        class RecoveringBot:
            def __init__(self) -> None:
                self.calls = 0

            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                self.calls += 1
                if self.calls == 1:
                    return [update]
                channel._running = False
                return []

        bot_factory = Mock(side_effect=[FailingBot(), FailingBot(), RecoveringBot()])
        fake_module = SimpleNamespace(Bot=bot_factory)
        channel._running = True
        with (
            patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()),
            patch.dict(sys.modules, {"telegram": fake_module}),
        ):
            await channel._poll_loop()

        signals = channel.signals()
        assert emitted == ["stabilized"]
        assert channel._connected is True
        assert channel._offset == 101
        assert signals["reconnect_count"] == 2
        assert signals["send_auth_breaker_open"] is False
        assert signals["typing_auth_breaker_open"] is False

    asyncio.run(_scenario())


def test_telegram_redelivery_reprocesses_after_failed_emit_then_commits_offset(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []
        attempts = 0

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, metadata
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("boom")
            emitted.append(text)

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        offset_path = tmp_path / "offset.json"
        _bind_offset_path(channel, offset_path)

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        try:
            await channel._handle_update(update)
            raise AssertionError("expected first emit failure")
        except RuntimeError:
            pass

        assert attempts == 1
        assert emitted == []
        assert channel._offset == 0
        assert not offset_path.exists()

        processed_ok = await channel._handle_update(update)
        assert processed_ok is True
        channel._begin_safe_offset_update(int(update.update_id))
        channel._complete_safe_offset_update(int(update.update_id))

        assert attempts == 2
        assert emitted == ["hello"]
        assert channel._offset == 101
        persisted = json.loads(offset_path.read_text(encoding="utf-8"))
        assert persisted["safe_update_id"] == 100
        assert persisted["next_offset"] == 101

    asyncio.run(_scenario())


def test_telegram_typing_starts_on_inbound_and_stops_before_outbound_send() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 1.0,
                "typing_timeout_s": 0.5,
            }
        )

        typing_started = asyncio.Event()

        class FakeBot:
            def __init__(self) -> None:
                self.typing_calls = 0
                self.send_calls = 0

            async def send_chat_action(self, **kwargs):
                del kwargs
                self.typing_calls += 1
                typing_started.set()
                await asyncio.sleep(0.5)

            async def send_message(self, **kwargs):
                del kwargs
                assert "42" not in channel._typing_tasks
                self.send_calls += 1

        bot = FakeBot()
        channel.bot = bot
        channel._running = True

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, text, metadata
            await asyncio.wait_for(typing_started.wait(), timeout=1.0)
            await channel.send(target="42", text="response")

        channel.on_message = _on_message

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=100,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert bot.typing_calls >= 1
        assert bot.send_calls == 1
        assert "42" not in channel._typing_tasks

    asyncio.run(_scenario())


def test_telegram_typing_stops_after_inbound_handler_without_immediate_reply() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 1.0,
                "typing_timeout_s": 0.5,
            }
        )

        typing_started = asyncio.Event()

        class FakeBot:
            def __init__(self) -> None:
                self.typing_calls = 0

            async def send_chat_action(self, **kwargs):
                del kwargs
                self.typing_calls += 1
                typing_started.set()
                await asyncio.sleep(0.5)

        channel.bot = FakeBot()
        channel._running = True

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, text, metadata
            await asyncio.wait_for(typing_started.wait(), timeout=1.0)

        channel.on_message = _on_message

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="hello",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=11,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=101,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        await channel._handle_update(update)

        assert channel.bot.typing_calls >= 1
        assert "42" not in channel._typing_tasks

    asyncio.run(_scenario())


def test_telegram_typing_keepalive_uses_chat_and_thread_context() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 0.2,
            }
        )

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_chat_action(self, **kwargs):
                self.calls.append(kwargs)

            async def send_message(self, **kwargs):
                del kwargs
                return True

        bot = FakeBot()
        channel.bot = bot
        channel._running = True

        channel._start_typing_keepalive(chat_id="42", message_thread_id=7)
        await asyncio.sleep(0.03)
        await channel.send(target="42:7", text="hello")

        assert any(call.get("message_thread_id") == 7 for call in bot.calls)
        assert "42:7" not in channel._typing_tasks

    asyncio.run(_scenario())


def test_telegram_typing_keepalive_normalizes_general_topic_thread_key() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 0.2,
            }
        )

        class FakeBot:
            def __init__(self) -> None:
                self.chat_action_calls: list[dict[str, object]] = []

            async def send_chat_action(self, **kwargs):
                self.chat_action_calls.append(kwargs)

            async def send_message(self, **kwargs):
                del kwargs
                return True

        bot = FakeBot()
        channel.bot = bot
        channel._running = True

        channel._start_typing_keepalive(chat_id="-10042", message_thread_id=1)
        await asyncio.sleep(0.03)

        assert "-10042" in channel._typing_tasks
        assert "-10042:1" not in channel._typing_tasks
        assert bot.chat_action_calls
        assert all("message_thread_id" not in call for call in bot.chat_action_calls)

        await channel.send(target="-10042:1", text="hello")
        assert "-10042" not in channel._typing_tasks

    asyncio.run(_scenario())


def test_telegram_typing_keepalive_duplicate_start_uses_single_worker_per_chat() -> (
    None
):
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 1.0,
                "typing_timeout_s": 0.5,
            }
        )

        started = asyncio.Event()

        class FakeBot:
            async def send_chat_action(self, **kwargs):
                del kwargs
                started.set()
                await asyncio.sleep(0.5)

            async def send_message(self, **kwargs):
                return kwargs

        channel.bot = FakeBot()
        channel._running = True
        create_task_calls = 0
        real_create_task = asyncio.create_task

        def _tracking_create_task(coro):
            nonlocal create_task_calls
            create_task_calls += 1
            return real_create_task(coro)

        with patch(
            "clawlite.channels.telegram.asyncio.create_task",
            side_effect=_tracking_create_task,
        ):
            channel._start_typing_keepalive(chat_id="42")
            channel._start_typing_keepalive(chat_id="42")
            await asyncio.wait_for(started.wait(), timeout=1.0)

        assert create_task_calls == 1
        assert "42" in channel._typing_tasks

        await channel._stop_typing_keepalive(chat_id="42")
        assert "42" not in channel._typing_tasks

    asyncio.run(_scenario())


def test_telegram_typing_thread_not_found_retries_without_thread_context() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 0.2,
                "typing_timeout_s": 0.2,
            }
        )

        threadless_retry_succeeded = asyncio.Event()

        class ThreadNotFoundError(RuntimeError):
            status_code = 400

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def send_chat_action(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("message_thread_id") == 7:
                    raise ThreadNotFoundError("Bad Request: message thread not found")
                threadless_retry_succeeded.set()
                return True

            async def send_message(self, **kwargs):
                return kwargs

        bot = FakeBot()
        channel.bot = bot
        channel._running = True

        channel._start_typing_keepalive(chat_id="42", message_thread_id=7)
        await asyncio.wait_for(threadless_retry_succeeded.wait(), timeout=1.0)
        await channel._stop_typing_keepalive(chat_id="42", message_thread_id=7)

        assert bot.calls[0]["message_thread_id"] == 7
        assert any("message_thread_id" not in call for call in bot.calls[1:])
        assert "42:7" not in channel._typing_tasks

    asyncio.run(_scenario())


def test_telegram_typing_auth_breaker_suppresses_repeated_calls_when_open() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 0.2,
                "typing_circuit_failure_threshold": 1,
                "typing_circuit_cooldown_s": 10.0,
            }
        )

        first_call = asyncio.Event()
        second_call = asyncio.Event()

        class AuthError(RuntimeError):
            status_code = 401

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def send_chat_action(self, **kwargs):
                del kwargs
                self.calls += 1
                if self.calls == 1:
                    first_call.set()
                if self.calls >= 2:
                    second_call.set()
                raise AuthError("unauthorized")

            async def send_message(self, **kwargs):
                return kwargs

        bot = FakeBot()
        channel.bot = bot
        channel._running = True

        channel._start_typing_keepalive(chat_id="42")
        await asyncio.wait_for(first_call.wait(), timeout=1.0)

        try:
            await asyncio.wait_for(second_call.wait(), timeout=0.1)
            raise AssertionError("typing breaker should suppress repeated auth calls")
        except asyncio.TimeoutError:
            pass

        await channel._stop_typing_keepalive(chat_id="42")
        assert bot.calls == 1

    asyncio.run(_scenario())


def test_telegram_typing_transient_failures_do_not_break_send_path() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 1.0,
                "typing_timeout_s": 0.2,
            }
        )

        typing_failed = asyncio.Event()

        class FakeBot:
            def __init__(self) -> None:
                self.send_calls = 0

            async def send_chat_action(self, **kwargs):
                del kwargs
                typing_failed.set()
                raise TimeoutError("timed out")

            async def send_message(self, **kwargs):
                del kwargs
                self.send_calls += 1

        bot = FakeBot()
        channel.bot = bot
        channel._running = True
        channel._start_typing_keepalive(chat_id="42")
        await asyncio.wait_for(typing_failed.wait(), timeout=1.0)

        out = await channel.send(target="42", text="hello")

        assert out == "telegram:sent:1"
        assert bot.send_calls == 1
        assert "42" not in channel._typing_tasks

    asyncio.run(_scenario())


def test_telegram_signals_track_retry_after_and_ttl_stop() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_retry_attempts": 2,
                "send_backoff_base_s": 0.01,
                "send_backoff_max_s": 0.01,
                "send_backoff_jitter": 0.0,
                "typing_enabled": True,
                "typing_interval_s": 0.01,
                "typing_max_ttl_s": 1.0,
            }
        )

        class RetryAfterError(RuntimeError):
            status_code = 429

            def __init__(self) -> None:
                super().__init__("too many requests")
                self.retry_after = 0.01

        class FakeBot:
            def __init__(self) -> None:
                self.send_calls = 0

            async def send_chat_action(self, **kwargs):
                del kwargs
                return True

            async def send_message(self, **kwargs):
                del kwargs
                self.send_calls += 1
                if self.send_calls == 1:
                    raise RetryAfterError()
                return True

        bot = FakeBot()
        channel.bot = bot
        channel._running = True
        channel._start_typing_keepalive(chat_id="42")
        await asyncio.sleep(1.1)

        out = await channel.send(target="42", text="hello")

        assert out == "telegram:sent:1"
        signals = channel.signals()
        assert signals["send_retry_count"] >= 1
        assert signals["send_retry_after_count"] >= 1
        assert signals["typing_ttl_stop_count"] >= 1

    asyncio.run(_scenario())


def test_telegram_send_soak_retries_grow_predictably_without_breaker_open() -> None:
    async def _scenario() -> None:
        total_messages = 12
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_retry_attempts": 2,
                "send_backoff_base_s": 0.01,
                "send_backoff_max_s": 0.01,
                "send_backoff_jitter": 0.0,
                "send_circuit_failure_threshold": 2,
            }
        )

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def send_message(self, **kwargs):
                del kwargs
                self.calls += 1
                if self.calls % 2 == 1:
                    raise TimeoutError("timed out")
                return True

        bot = FakeBot()
        channel.bot = bot

        with patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()):
            for _ in range(total_messages):
                out = await channel.send(target="42", text="hello")
                assert out == "telegram:sent:1"

        signals = channel.signals()
        assert bot.calls == total_messages * 2
        assert signals["send_retry_count"] == total_messages
        assert signals["send_retry_after_count"] == 0
        assert signals["send_auth_breaker_open"] is False
        assert signals["send_auth_breaker_open_count"] == 0
        assert signals["send_auth_breaker_close_count"] == 0

    asyncio.run(_scenario())


def test_telegram_send_mixed_chaos_chunking_retry_after_timeout_then_success() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_retry_attempts": 4,
                "send_backoff_base_s": 0.01,
                "send_backoff_max_s": 0.01,
                "send_backoff_jitter": 0.0,
                "send_circuit_failure_threshold": 2,
            }
        )
        text = ("A" * 4000) + ("B" * 128)
        chunks = split_message(text)
        assert len(chunks) == 2

        class FormattingError(RuntimeError):
            status_code = 400

        class RetryAfterError(RuntimeError):
            status_code = 429

            def __init__(self, retry_after: float) -> None:
                super().__init__("too many requests")
                self.retry_after = retry_after

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []
                self.successful_chunks: list[str] = []
                self._chunk_attempts: dict[int, int] = {0: 0, 1: 0}

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                chunk_idx = 0 if kwargs["text"] == chunks[0] else 1
                self._chunk_attempts[chunk_idx] += 1
                attempt = self._chunk_attempts[chunk_idx]

                if chunk_idx == 0:
                    if attempt == 1 and kwargs.get("parse_mode") == "HTML":
                        raise FormattingError("can't parse entities")
                    if attempt == 2:
                        raise TimeoutError("timed out")
                else:
                    if attempt == 1:
                        raise RetryAfterError(0.25)

                self.successful_chunks.append(kwargs["text"])
                return True

        bot = FakeBot()
        channel.bot = bot

        sleep_mock = AsyncMock()
        with patch("clawlite.channels.telegram.asyncio.sleep", new=sleep_mock):
            out = await channel.send(target="42", text=text)

        assert out == "telegram:sent:2"
        assert bot.successful_chunks == chunks
        assert bot._chunk_attempts == {0: 3, 1: 2}

        first_chunk_calls = [call for call in bot.calls if call["text"] == chunks[0]]
        assert first_chunk_calls[0]["parse_mode"] == "HTML"
        assert first_chunk_calls[1]["parse_mode"] is None

        signals = channel.signals()
        assert signals["send_retry_count"] == 2
        assert signals["send_retry_after_count"] == 1
        assert signals["send_auth_breaker_open"] is False
        assert signals["send_auth_breaker_open_count"] == 0
        assert signals["send_auth_breaker_close_count"] == 0

        sleep_delays = [call.args[0] for call in sleep_mock.await_args_list]
        assert len(sleep_delays) == 2
        assert 0.0 < sleep_delays[0] <= 0.02
        assert sleep_delays[1] == 0.25

    asyncio.run(_scenario())


def test_telegram_polling_recovery_matrix_multiple_reconnects_then_stable_updates(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "reconnect_initial_s": 0.01,
                "reconnect_max_s": 0.02,
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        offset_path = tmp_path / "offset.json"
        _bind_offset_path(channel, offset_path)

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")

        def _update(update_id: int, text: str):
            msg = SimpleNamespace(
                text=text,
                caption=None,
                chat_id=42,
                from_user=user,
                message_id=10 + update_id,
                chat=chat,
                date=None,
                edit_date=None,
                reply_to_message=None,
            )
            return SimpleNamespace(
                update_id=update_id,
                message=msg,
                edited_message=None,
                effective_message=msg,
            )

        updates = [
            _update(100, "u100"),
            _update(101, "u101"),
            _update(102, "u102"),
        ]

        class FailingBot:
            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                raise TimeoutError("timed out")

        class StableBot:
            def __init__(self) -> None:
                self.calls = 0

            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                self.calls += 1
                if self.calls == 1:
                    return [updates[0], updates[1]]
                if self.calls == 2:
                    return [updates[2]]
                channel._running = False
                return []

        bot_factory = Mock(
            side_effect=[FailingBot(), FailingBot(), FailingBot(), StableBot()]
        )
        fake_module = SimpleNamespace(Bot=bot_factory)

        channel._running = True
        with (
            patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()),
            patch.dict(sys.modules, {"telegram": fake_module}),
        ):
            await channel._poll_loop()

        signals = channel.signals()
        assert emitted == ["u100", "u101", "u102"]
        assert channel._offset == 103
        persisted = json.loads(offset_path.read_text(encoding="utf-8"))
        assert persisted["safe_update_id"] == 102
        assert persisted["next_offset"] == 103
        assert channel._connected is True
        assert signals["reconnect_count"] == 3
        assert signals["send_auth_breaker_open"] is False
        assert signals["typing_auth_breaker_open"] is False

    asyncio.run(_scenario())


def test_telegram_polling_stale_update_is_skipped_and_counted(tmp_path: Path) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        _bind_offset_path(channel, tmp_path / "offset.json")
        channel._force_commit_offset_update(199)

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")
        message = SimpleNamespace(
            text="stale",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        stale_update = SimpleNamespace(
            update_id=150,
            message=message,
            edited_message=None,
            effective_message=message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def get_updates(self, *, offset, timeout, allowed_updates):
                del offset, timeout, allowed_updates
                self.calls += 1
                if self.calls == 1:
                    return [stale_update]
                channel._running = False
                return []

        channel.bot = FakeBot()
        channel._running = True
        await channel._poll_loop()

        assert emitted == []
        assert channel._offset == 200
        assert channel.signals()["polling_stale_update_skip_count"] == 1

    asyncio.run(_scenario())


def test_telegram_polling_duplicate_update_advances_offset_and_recovers(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)
            channel._running = False

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        offset_path = tmp_path / "offset.json"
        _bind_offset_path(channel, offset_path)
        channel._force_commit_offset_update(99)
        assert (
            channel._remember_update_dedupe_key("update:100", source="polling") is True
        )

        user = SimpleNamespace(
            id=1, username="alice", first_name="Alice", language_code="en"
        )
        chat = SimpleNamespace(type="private")

        duplicate_message = SimpleNamespace(
            text="already-seen",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=10,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        fresh_message = SimpleNamespace(
            text="fresh-after-duplicate",
            caption=None,
            chat_id=42,
            from_user=user,
            message_id=11,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        duplicate_update = SimpleNamespace(
            update_id=100,
            message=duplicate_message,
            edited_message=None,
            effective_message=duplicate_message,
        )
        fresh_update = SimpleNamespace(
            update_id=101,
            message=fresh_message,
            edited_message=None,
            effective_message=fresh_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.offsets: list[int] = []

            async def get_updates(self, *, offset, timeout, allowed_updates):
                del timeout, allowed_updates
                self.offsets.append(offset)
                if offset < 101:
                    return [duplicate_update]
                if offset == 101:
                    return [fresh_update]
                channel._running = False
                return []

        channel.bot = FakeBot()
        channel._running = True
        with patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()):
            await channel._poll_loop()

        assert emitted == ["fresh-after-duplicate"]
        assert channel._offset == 102
        persisted = json.loads(offset_path.read_text(encoding="utf-8"))
        assert persisted["safe_update_id"] == 101
        assert persisted["next_offset"] == 102
        assert channel.bot.offsets[:2] == [100, 101]
        assert channel.signals()["update_duplicate_skip_count"] == 1

    asyncio.run(_scenario())


def test_telegram_send_auth_breaker_close_count_tracks_natural_cooldown() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "send_circuit_failure_threshold": 1,
                "send_circuit_cooldown_s": 60,
            }
        )

        class AuthError(RuntimeError):
            status_code = 401

        class FakeBot:
            async def send_message(self, **kwargs):
                del kwargs
                raise AuthError("unauthorized")

        channel.bot = FakeBot()

        with patch("clawlite.channels.telegram.time.monotonic", return_value=100.0):
            try:
                await channel.send(target="42", text="hello")
                raise AssertionError("expected auth failure")
            except AuthError:
                pass

        with patch("clawlite.channels.telegram.time.monotonic", return_value=161.0):
            signals = channel.signals()

        assert signals["send_auth_breaker_open_count"] == 1
        assert signals["send_auth_breaker_close_count"] == 1
        assert signals["send_auth_breaker_open"] is False

    asyncio.run(_scenario())


def test_telegram_webhook_mode_start_sets_webhook_and_stop_deletes_webhook() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "mode": "webhook",
                "webhook_url": "https://example.com/hook",
                "webhook_secret": "secret-1",
            }
        )

        class FakeBot:
            def __init__(self, token: str) -> None:
                assert token == "x:token"
                self.set_calls: list[dict] = []
                self.delete_calls: list[dict] = []

            async def set_webhook(self, **kwargs):
                self.set_calls.append(kwargs)
                return True

            async def delete_webhook(self, **kwargs):
                self.delete_calls.append(kwargs)
                return True

        fake_module = SimpleNamespace(Bot=FakeBot)
        with patch.dict(sys.modules, {"telegram": fake_module}):
            await channel.start()
            assert channel.running is True
            assert channel.webhook_mode_active is True
            assert channel._task is None
            bot = channel.bot
            assert bot is not None
            assert len(bot.set_calls) == 1
            assert bot.set_calls[0]["url"] == "https://example.com/hook"
            assert bot.set_calls[0]["secret_token"] == "secret-1"
            assert bot.set_calls[0]["allowed_updates"] == [
                "message",
                "edited_message",
                "inline_query",
                "chosen_inline_result",
                "business_message",
                "edited_business_message",
                "deleted_business_messages",
                "business_connection",
                "callback_query",
                "shipping_query",
                "pre_checkout_query",
                "poll",
                "poll_answer",
                "my_chat_member",
                "chat_member",
                "chat_join_request",
                "message_reaction",
                "message_reaction_count",
                "chat_boost",
                "removed_chat_boost",
                "purchased_paid_media",
                "channel_post",
                "edited_channel_post",
            ]
            await channel.stop()

        assert len(bot.delete_calls) == 1
        assert bot.delete_calls[0]["drop_pending_updates"] is False
        signals = channel.signals()
        assert signals["webhook_set_count"] == 1
        assert signals["webhook_delete_count"] == 1
        assert signals["webhook_mode_active"] is False

    asyncio.run(_scenario())


def test_telegram_operator_status_reports_offset_and_pairing_state(tmp_path: Path) -> None:
    channel = TelegramChannel(
        config={
            "token": "12345:token",
            "offset_state_path": str(tmp_path / "offset.json"),
            "pairing_state_path": str(tmp_path / "pairing.json"),
        }
    )
    channel._force_commit_offset_update(55)
    channel._pairing_store.issue_request(chat_id="1", user_id="2", username="alice")

    payload = channel.operator_status()

    assert payload["mode"] == "polling"
    assert payload["webhook_requested"] is False
    assert payload["offset_next"] == 56
    assert payload["offset_watermark_update_id"] == 55
    assert payload["pairing_pending_count"] == 1
    assert payload["pairing_approved_count"] == 0
    assert any("pending review" in row for row in payload["hints"])


def test_telegram_operator_status_surfaces_transport_hints(tmp_path: Path) -> None:
    channel = TelegramChannel(
        config={
            "token": "12345:token",
            "mode": "webhook",
            "offset_state_path": str(tmp_path / "offset.json"),
        }
    )
    channel._last_error = "webhook_broken"
    channel._offset_store.begin(101)

    payload = channel.operator_status()

    assert any("no webhook URL is configured" in row for row in payload["hints"])
    assert any("not active" in row for row in payload["hints"])
    assert any("still pending" in row for row in payload["hints"])
    assert any("transport error" in row for row in payload["hints"])


def test_telegram_operator_refresh_transport_refreshes_webhook_and_reloads_offset(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "mode": "webhook",
                "webhook_url": "https://example.com/hook",
                "webhook_secret": "secret-1",
                "offset_state_path": str(tmp_path / "offset.json"),
            }
        )
        channel._force_commit_offset_update(88)

        class FakeBot:
            def __init__(self, token: str) -> None:
                assert token == "x:token"
                self.set_calls: list[dict[str, object]] = []
                self.delete_calls: list[dict[str, object]] = []

            async def set_webhook(self, **kwargs):
                self.set_calls.append(kwargs)
                return True

            async def delete_webhook(self, **kwargs):
                self.delete_calls.append(kwargs)
                return True

        fake_module = SimpleNamespace(Bot=FakeBot)
        with patch.dict(sys.modules, {"telegram": fake_module}):
            payload = await channel.operator_refresh_transport()

        assert payload["offset_reloaded"] is True
        assert payload["webhook_deleted"] is True
        assert payload["webhook_activated"] is True
        assert payload["status"]["offset_next"] == 89
        assert payload["status"]["webhook_mode_active"] is True

    asyncio.run(_scenario())


def test_telegram_operator_approve_pairing_returns_status(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "12345:token",
                "pairing_state_path": str(tmp_path / "pairing.json"),
            }
        )
        request, _created = channel._pairing_store.issue_request(chat_id="1", user_id="2", username="alice")

        payload = await channel.operator_approve_pairing(str(request["code"]))

        assert payload["ok"] is True
        assert payload["request"]["chat_id"] == "1"
        assert payload["status"]["pairing_pending_count"] == 0
        assert payload["status"]["pairing_approved_count"] >= 1

    asyncio.run(_scenario())


def test_telegram_operator_force_commit_offset_returns_status(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "12345:token",
                "offset_state_path": str(tmp_path / "offset.json"),
            }
        )

        payload = await channel.operator_force_commit_offset(144)

        assert payload["ok"] is True
        assert payload["update_id"] == 144
        assert payload["status"]["offset_watermark_update_id"] == 144
        assert payload["status"]["offset_next"] == 145

    asyncio.run(_scenario())


def test_telegram_operator_sync_next_offset_returns_status(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "12345:token",
                "offset_state_path": str(tmp_path / "offset.json"),
            }
        )

        payload = await channel.operator_sync_next_offset(145)

        assert payload["ok"] is True
        assert payload["next_offset"] == 145
        assert payload["status"]["offset_watermark_update_id"] == 144
        assert payload["status"]["offset_next"] == 145

    asyncio.run(_scenario())


def test_telegram_operator_sync_next_offset_requires_allow_reset_for_zero(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "12345:token",
                "offset_state_path": str(tmp_path / "offset.json"),
            }
        )

        payload = await channel.operator_sync_next_offset(0, allow_reset=False)

        assert payload["ok"] is False
        assert payload["error"] == "allow_reset_required"

    asyncio.run(_scenario())


def test_telegram_operator_reject_pairing_returns_status(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "12345:token",
                "pairing_state_path": str(tmp_path / "pairing.json"),
            }
        )
        request, _created = channel._pairing_store.issue_request(chat_id="1", user_id="2", username="alice")

        payload = await channel.operator_reject_pairing(str(request["code"]))

        assert payload["ok"] is True
        assert payload["request"]["chat_id"] == "1"
        assert payload["status"]["pairing_pending_count"] == 0

    asyncio.run(_scenario())


def test_telegram_operator_revoke_pairing_returns_status(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "12345:token",
                "pairing_state_path": str(tmp_path / "pairing.json"),
            }
        )
        request, _created = channel._pairing_store.issue_request(chat_id="1", user_id="2", username="alice")
        await channel.operator_approve_pairing(str(request["code"]))

        payload = await channel.operator_revoke_pairing("@alice")

        assert payload["ok"] is True
        assert payload["removed_entry"] == "@alice"
        assert "@alice" not in payload["approved_entries"]

    asyncio.run(_scenario())


def test_telegram_webhook_missing_config_falls_back_to_polling() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token", "mode": "webhook"})

        async def _fake_poll_loop() -> None:
            await asyncio.sleep(3600)

        channel._poll_loop = _fake_poll_loop  # type: ignore[method-assign]
        await channel.start()

        assert channel.running is True
        assert channel.webhook_mode_active is False
        assert channel._task is not None
        assert channel._task.done() is False
        signals = channel.signals()
        assert signals["webhook_fallback_to_polling_count"] == 1

        await channel.stop()

    asyncio.run(_scenario())


def test_telegram_handle_webhook_update_normalizes_callback_payload_and_dedupes(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.acks: list[dict[str, object]] = []

            async def answer_callback_query(self, **kwargs):
                self.acks.append(kwargs)
                return True

        channel.bot = FakeBot()
        payload = {
            "update_id": 900,
            "callback_query": {
                "id": "cq-raw-1",
                "data": "action:raw",
                "chat_instance": "inst-raw",
                "from": {"id": 7, "username": "alice"},
                "message": {
                    "message_id": 55,
                    "message_thread_id": 4,
                    "chat": {"id": 42},
                },
            },
        }

        processed_first = await channel.handle_webhook_update(payload)
        processed_duplicate = await channel.handle_webhook_update(payload)

        assert processed_first is True
        assert processed_duplicate is False
        assert len(channel.bot.acks) == 1
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:42"
        assert user_id == "7"
        assert text == "action:raw"
        assert metadata["channel"] == "telegram"
        assert metadata["chat_id"] == "42"
        assert metadata["callback_query_id"] == "cq-raw-1"
        assert metadata["message_thread_id"] == 4
        signals = channel.signals()
        assert signals["webhook_update_received_count"] == 2
        assert signals["webhook_update_duplicate_count"] == 1

    asyncio.run(_scenario())


def test_telegram_webhook_success_persists_dedupe_state_before_restart(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        dedupe_path = tmp_path / "telegram-dedupe.json"
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
            },
            on_message=_on_message,
        )

        payload = {
            "update_id": 901,
            "message": {
                "message_id": 55,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7, "username": "alice"},
                "text": "persist me",
            },
        }

        processed = await channel.handle_webhook_update(payload)

        assert processed is True
        persisted = json.loads(dedupe_path.read_text(encoding="utf-8"))
        assert "update:901" in persisted["keys"]

        reloaded = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
            },
        )
        duplicate = await reloaded.handle_webhook_update(payload)
        assert duplicate is False

    asyncio.run(_scenario())


def test_telegram_webhook_refreshes_persisted_dedupe_across_live_instances(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted_a: list[str] = []
        emitted_b: list[str] = []
        dedupe_path = tmp_path / "telegram-dedupe.json"

        async def _on_message_a(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            del session_id, user_id, metadata
            emitted_a.append(text)

        async def _on_message_b(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            del session_id, user_id, metadata
            emitted_b.append(text)

        channel_a = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
            },
            on_message=_on_message_a,
        )
        channel_b = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(dedupe_path),
            },
            on_message=_on_message_b,
        )

        payload = {
            "update_id": 902,
            "message": {
                "message_id": 56,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7, "username": "alice"},
                "text": "shared dedupe",
            },
        }

        first = await channel_a.handle_webhook_update(payload)
        duplicate = await channel_b.handle_webhook_update(payload)

        assert first is True
        assert duplicate is False
        assert emitted_a == ["shared dedupe"]
        assert emitted_b == []
        assert channel_b.signals()["webhook_update_duplicate_count"] == 1

    asyncio.run(_scenario())


def test_telegram_webhook_failed_processing_allows_redelivery_then_commits_dedupe(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            }
        )
        payload = {
            "update_id": 990,
            "message": {
                "message_id": 55,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7, "username": "alice"},
                "text": "retry me",
            },
        }

        attempts = 0

        async def _flaky_handle(_: object) -> bool:
            nonlocal attempts
            attempts += 1
            return attempts >= 2

        channel._handle_update = _flaky_handle  # type: ignore[method-assign]

        first = await channel.handle_webhook_update(payload)
        second = await channel.handle_webhook_update(payload)
        third = await channel.handle_webhook_update(payload)

        assert first is False
        assert second is True
        assert third is False
        assert attempts == 2
        signals = channel.signals()
        assert signals["update_duplicate_skip_count"] == 1
        assert signals["webhook_update_duplicate_count"] == 1

    asyncio.run(_scenario())


def test_telegram_dedupe_skips_duplicate_callback_query_without_update_id(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )

        class FakeBot:
            def __init__(self) -> None:
                self.acks: list[dict[str, object]] = []

            async def answer_callback_query(self, **kwargs):
                self.acks.append(kwargs)
                return True

        channel.bot = FakeBot()
        payload = {
            "callback_query": {
                "id": "cq-dup-no-update",
                "data": "action:raw",
                "from": {"id": 7, "username": "alice"},
                "message": {"message_id": 55, "chat": {"id": 42}},
            }
        }

        first = await channel.handle_webhook_update(payload)
        duplicate = await channel.handle_webhook_update(payload)

        assert first is True
        assert duplicate is False
        assert len(emitted) == 1
        signals = channel.signals()
        assert signals["update_duplicate_skip_count"] == 1

    asyncio.run(_scenario())


def test_telegram_dedupe_is_unified_across_polling_and_webhook(tmp_path: Path) -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            }
        )
        assert (
            channel._remember_update_dedupe_key("update:991", source="polling") is True
        )

        payload = {
            "update_id": 991,
            "message": {
                "message_id": 56,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7, "username": "alice"},
                "text": "duplicate across mode",
            },
        }

        processed = await channel.handle_webhook_update(payload)

        assert processed is False
        signals = channel.signals()
        assert signals["update_duplicate_skip_count"] == 1
        assert signals["webhook_update_duplicate_count"] == 1

    asyncio.run(_scenario())


def test_telegram_dedupe_skips_duplicate_message_key_without_update_id(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        payload = {
            "message": {
                "message_id": 90,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7, "username": "alice"},
                "text": "raw message",
            }
        }

        first = await channel.handle_webhook_update(payload)
        duplicate = await channel.handle_webhook_update(payload)

        assert first is True
        assert duplicate is False
        assert len(emitted) == 1
        signals = channel.signals()
        assert signals["update_duplicate_skip_count"] == 1

    asyncio.run(_scenario())


def test_telegram_webhook_out_of_order_updates_buffer_until_gap_closes(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        _bind_offset_path(channel, tmp_path / "offset.json")
        channel._force_commit_offset_update(900)

        payload_902 = {
            "update_id": 902,
            "message": {
                "message_id": 57,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7, "username": "alice"},
                "text": "u902",
            },
        }
        payload_901 = {
            "update_id": 901,
            "message": {
                "message_id": 56,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 7, "username": "alice"},
                "text": "u901",
            },
        }

        processed_902 = await channel.handle_webhook_update(payload_902)
        assert processed_902 is True
        assert channel._offset == 901

        processed_901 = await channel.handle_webhook_update(payload_901)
        duplicate_902 = await channel.handle_webhook_update(payload_902)

        assert processed_901 is True
        assert duplicate_902 is False
        assert emitted == ["u902", "u901"]
        assert channel._offset == 903
        persisted = json.loads((tmp_path / "offset.json").read_text(encoding="utf-8"))
        assert persisted["safe_update_id"] == 902
        assert persisted["completed_update_ids"] == []
        signals = channel.signals()
        assert signals["webhook_stale_update_skip_count"] == 1

    asyncio.run(_scenario())


def test_telegram_channel_post_is_forwarded() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        chat = SimpleNamespace(type="channel")
        post = SimpleNamespace(
            text="channel hello",
            caption=None,
            chat_id=-100123,
            from_user=None,
            message_id=30,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=201,
            message=None,
            edited_message=None,
            channel_post=post,
            edited_channel_post=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:-100123"
        assert user_id == "-100123"
        assert text == "channel hello"
        assert metadata["channel"] == "telegram"
        assert metadata["chat_id"] == "-100123"
        assert metadata["is_edit"] is False

    asyncio.run(_scenario())


def test_telegram_edited_channel_post_is_forwarded_as_edit() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        chat = SimpleNamespace(type="channel")
        post = SimpleNamespace(
            text="channel edit",
            caption=None,
            chat_id=-100124,
            from_user=None,
            message_id=31,
            chat=chat,
            date=None,
            edit_date=None,
            reply_to_message=None,
        )
        update = SimpleNamespace(
            update_id=202,
            message=None,
            edited_message=None,
            channel_post=None,
            edited_channel_post=post,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:-100124"
        assert user_id == "-100124"
        assert text == "channel edit"
        assert metadata["chat_id"] == "-100124"
        assert metadata["is_edit"] is True

    asyncio.run(_scenario())


def test_telegram_handle_webhook_update_normalizes_channel_post_payload(
    tmp_path: Path,
) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "dedupe_state_path": str(tmp_path / "telegram-dedupe.json"),
            },
            on_message=_on_message,
        )
        payload = {
            "update_id": 901,
            "channel_post": {
                "message_id": 90,
                "chat": {"id": -100222, "type": "channel"},
                "text": "raw channel",
            },
        }

        processed = await channel.handle_webhook_update(payload)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:-100222"
        assert user_id == "-100222"
        assert text == "raw channel"
        assert metadata["chat_id"] == "-100222"
        assert metadata["is_edit"] is False

    asyncio.run(_scenario())


def test_telegram_chat_member_update_emits_normalized_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        update = SimpleNamespace(
            update_id=701,
            chat_member=SimpleNamespace(
                chat=SimpleNamespace(id=-10042, type="supergroup"),
                from_user=SimpleNamespace(id=5, username="owner"),
                old_chat_member=SimpleNamespace(status="member"),
                new_chat_member=SimpleNamespace(
                    status="administrator",
                    user=SimpleNamespace(id=7, username="alice"),
                ),
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:-10042"
        assert user_id == "7"
        assert text == "[telegram chat member] member -> administrator"
        assert metadata["update_kind"] == "chat_member"
        assert metadata["member_user_id"] == 7
        assert metadata["old_status"] == "member"
        assert metadata["new_status"] == "administrator"

    asyncio.run(_scenario())


def test_telegram_chat_join_request_emits_normalized_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        update = SimpleNamespace(
            update_id=702,
            chat_join_request=SimpleNamespace(
                chat=SimpleNamespace(id=-10055, type="supergroup"),
                from_user=SimpleNamespace(id=8, username="bob"),
                bio="hello",
                invite_link="https://example.com/invite",
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:-10055"
        assert user_id == "8"
        assert text == "[telegram chat join request]"
        assert metadata["update_kind"] == "chat_join_request"
        assert metadata["bio"] == "hello"
        assert metadata["invite_link"] == "https://example.com/invite"

    asyncio.run(_scenario())


def test_telegram_deleted_business_messages_emit_normalized_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        update = SimpleNamespace(
            update_id=703,
            deleted_business_messages=SimpleNamespace(
                chat=SimpleNamespace(id=6001, type="private"),
                business_connection_id="bc-1",
                message_ids=[11, 12],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        metadata = emitted[0][3]
        assert metadata["update_kind"] == "deleted_business_messages"
        assert metadata["business_connection_id"] == "bc-1"
        assert metadata["message_ids"] == [11, 12]

    asyncio.run(_scenario())


def test_telegram_chat_boost_update_emits_normalized_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        update = SimpleNamespace(
            update_id=704,
            chat_boost=SimpleNamespace(
                chat=SimpleNamespace(id=-10077, type="supergroup"),
                boost=SimpleNamespace(
                    boost_id="boost-1",
                    source=SimpleNamespace(
                        user=SimpleNamespace(id=9, username="carol")
                    ),
                ),
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:-10077"
        assert user_id == "9"
        assert text == "[telegram chat boost]"
        assert metadata["update_kind"] == "chat_boost"
        assert metadata["boost_id"] == "boost-1"

    asyncio.run(_scenario())


def test_telegram_purchased_paid_media_emits_normalized_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict[str, object]
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        update = SimpleNamespace(
            update_id=705,
            purchased_paid_media=SimpleNamespace(
                chat=SimpleNamespace(id=6010, type="private"),
                user=SimpleNamespace(id=14, username="dora"),
                payload="media-token-1",
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:6010"
        assert user_id == "14"
        assert text == "[telegram purchased paid media]"
        assert metadata["update_kind"] == "purchased_paid_media"
        assert metadata["payload"] == "media-token-1"

    asyncio.run(_scenario())


def test_telegram_message_reaction_notifications_all_emits_event() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "reaction_notifications": "all"},
            on_message=_on_message,
        )
        update = SimpleNamespace(
            update_id=300,
            callback_query=None,
            message_reaction=SimpleNamespace(
                chat=SimpleNamespace(id=42),
                message_id=77,
                user=SimpleNamespace(id=7, username="alice", is_bot=False),
                old_reaction=[SimpleNamespace(emoji="👍")],
                new_reaction=[SimpleNamespace(emoji="👍"), SimpleNamespace(emoji="🔥")],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:42"
        assert user_id == "7"
        assert text == "[telegram reaction] 🔥"
        assert metadata["channel"] == "telegram"
        assert metadata["is_message_reaction"] is True
        assert metadata["chat_id"] == "42"
        assert metadata["message_id"] == 77
        assert metadata["user_id"] == "7"
        assert metadata["username"] == "alice"
        assert metadata["reaction_added"] == ["🔥"]
        assert metadata["reaction_new"] == ["👍", "🔥"]
        assert metadata["reaction_old"] == ["👍"]
        signals = channel.signals()
        assert signals["message_reaction_received_count"] == 1
        assert signals["message_reaction_emitted_count"] == 1

    asyncio.run(_scenario())


def test_telegram_message_reaction_notifications_off_blocks_event() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "reaction_notifications": "off"},
            on_message=_on_message,
        )
        update = SimpleNamespace(
            update_id=301,
            callback_query=None,
            message_reaction=SimpleNamespace(
                chat=SimpleNamespace(id=42),
                message_id=88,
                user=SimpleNamespace(id=8, username="bob", is_bot=False),
                old_reaction=[],
                new_reaction=[SimpleNamespace(emoji="👍")],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert emitted == []
        signals = channel.signals()
        assert signals["message_reaction_received_count"] == 1
        assert signals["message_reaction_blocked_count"] == 1
        assert signals["message_reaction_emitted_count"] == 0

    asyncio.run(_scenario())


def test_telegram_message_reaction_notifications_own_requires_sent_cache() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "reaction_notifications": "own"},
            on_message=_on_message,
        )

        class FakeBot:
            async def send_message(self, **kwargs):
                del kwargs
                return SimpleNamespace(message_id=99)

        channel.bot = FakeBot()

        blocked_update = SimpleNamespace(
            update_id=302,
            callback_query=None,
            message_reaction=SimpleNamespace(
                chat=SimpleNamespace(id=42),
                message_id=98,
                user=SimpleNamespace(id=9, username="carol", is_bot=False),
                old_reaction=[],
                new_reaction=[SimpleNamespace(emoji="🔥")],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )
        allowed_update = SimpleNamespace(
            update_id=303,
            callback_query=None,
            message_reaction=SimpleNamespace(
                chat=SimpleNamespace(id=42),
                message_id=99,
                user=SimpleNamespace(id=9, username="carol", is_bot=False),
                old_reaction=[],
                new_reaction=[SimpleNamespace(emoji="🔥")],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        blocked_processed = await channel._handle_update(blocked_update)
        send_out = await channel.send(target="42", text="seed")
        allowed_processed = await channel._handle_update(allowed_update)

        assert blocked_processed is True
        assert send_out == "telegram:sent:1"
        assert allowed_processed is True
        assert len(emitted) == 1
        assert emitted[0][0] == "telegram:42"
        assert emitted[0][1] == "9"
        assert emitted[0][2] == "[telegram reaction] 🔥"
        signals = channel.signals()
        assert signals["message_reaction_received_count"] == 2
        assert signals["message_reaction_blocked_count"] == 1
        assert signals["message_reaction_emitted_count"] == 1

    asyncio.run(_scenario())


def test_telegram_message_reaction_bot_user_is_ignored() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(
            session_id: str, user_id: str, text: str, metadata: dict
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "reaction_notifications": "all"},
            on_message=_on_message,
        )
        update = SimpleNamespace(
            update_id=304,
            callback_query=None,
            message_reaction=SimpleNamespace(
                chat=SimpleNamespace(id=42),
                message_id=100,
                user=SimpleNamespace(id=777, username="bot", is_bot=True),
                old_reaction=[],
                new_reaction=[SimpleNamespace(emoji="👍")],
            ),
            message=None,
            edited_message=None,
            effective_message=None,
        )

        processed = await channel._handle_update(update)

        assert processed is True
        assert emitted == []
        signals = channel.signals()
        assert signals["message_reaction_received_count"] == 1
        assert signals["message_reaction_ignored_bot_count"] == 1
        assert signals["message_reaction_emitted_count"] == 0
        assert signals["message_reaction_blocked_count"] == 0

    asyncio.run(_scenario())


def test_telegram_build_reply_keyboard_valid() -> None:
    from clawlite.channels.telegram import TelegramChannel
    ch = TelegramChannel.__new__(TelegramChannel)
    keyboard = [["Yes", "No"], ["Cancel"]]
    result = ch._build_reply_keyboard_reply_markup({"telegram_reply_keyboard": keyboard})
    assert result is not None
    if isinstance(result, dict):
        rows = result["keyboard"]
        assert rows[0][0]["text"] == "Yes"
        assert rows[0][1]["text"] == "No"
        assert rows[1][0]["text"] == "Cancel"


def test_telegram_build_reply_keyboard_remove() -> None:
    from clawlite.channels.telegram import TelegramChannel
    ch = TelegramChannel.__new__(TelegramChannel)
    result = ch._build_reply_keyboard_reply_markup({"telegram_reply_keyboard": False})
    assert result is not None
    if isinstance(result, dict):
        assert result.get("remove_keyboard") is True


def test_telegram_build_reply_keyboard_returns_none_without_key() -> None:
    from clawlite.channels.telegram import TelegramChannel
    ch = TelegramChannel.__new__(TelegramChannel)
    assert ch._build_reply_keyboard_reply_markup({}) is None


def test_telegram_build_reply_keyboard_invalid_row_returns_none() -> None:
    from clawlite.channels.telegram import TelegramChannel
    ch = TelegramChannel.__new__(TelegramChannel)
    assert ch._build_reply_keyboard_reply_markup({"telegram_reply_keyboard": [[123, None]]}) is None


def test_telegram_send_streaming_edits_message() -> None:
    """send_streaming() sends initial message then edits it as chunks arrive."""
    import asyncio

    sent_texts: list[str] = []
    edited_texts: list[str] = []

    from clawlite.core.engine import ProviderChunk

    async def fake_chunks():
        yield ProviderChunk(text="Hi ", accumulated="Hi ", done=False)
        yield ProviderChunk(text="there", accumulated="Hi there", done=True)

    from clawlite.channels.telegram import TelegramChannel

    ch = TelegramChannel.__new__(TelegramChannel)

    class FakeBot:
        async def send_message(self, chat_id, text, **kwargs):
            sent_texts.append(text)

            class Msg:
                message_id = 42

            return Msg()

        async def edit_message_text(self, text, chat_id, message_id, **kwargs):
            edited_texts.append(text)

    ch.bot = FakeBot()

    asyncio.run(ch.send_streaming(chat_id="123", chunks=fake_chunks()))

    assert len(sent_texts) == 1  # initial placeholder
    assert len(edited_texts) >= 1
    assert edited_texts[-1] == "Hi there"


def test_telegram_send_streaming_renders_markdown_html() -> None:
    import asyncio

    sent_texts: list[str] = []
    edits: list[dict[str, Any]] = []

    from clawlite.core.engine import ProviderChunk
    from clawlite.channels.telegram import TelegramChannel

    async def fake_chunks():
        yield ProviderChunk(text="**Hi** ", accumulated="**Hi** ", done=False)
        yield ProviderChunk(text="there", accumulated="**Hi** there", done=True)

    ch = TelegramChannel.__new__(TelegramChannel)

    class FakeBot:
        async def send_message(self, chat_id, text, **kwargs):
            sent_texts.append(text)

            class Msg:
                message_id = 42

            return Msg()

        async def edit_message_text(self, text, chat_id, message_id, **kwargs):
            edits.append({"text": text, "kwargs": kwargs})

    ch.bot = FakeBot()

    asyncio.run(ch.send_streaming(chat_id="123", chunks=fake_chunks()))

    assert len(sent_texts) == 1
    assert edits
    assert edits[-1]["text"] == "<b>Hi</b> there"
    assert edits[-1]["kwargs"]["parse_mode"] == "HTML"
