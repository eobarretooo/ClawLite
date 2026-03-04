from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from clawlite.channels.telegram import split_message
from clawlite.channels.telegram import TelegramCircuitOpenError
from clawlite.channels.telegram import TelegramChannel


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
    channel = TelegramChannel(config={"token": "x:token", "allowFrom": ["123", "@owner"]})
    assert channel._is_allowed_sender("123")
    assert channel._is_allowed_sender("777", "owner")
    assert not channel._is_allowed_sender("777", "guest")


def test_telegram_dm_policy_disabled_blocks_private_message() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "dm_policy": "disabled"},
            on_message=_on_message,
        )
        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "dm_policy": "allowlist", "dm_allow_from": ["123", "@owner"]},
            on_message=_on_message,
        )
        allowed_message = SimpleNamespace(
            text="allowed",
            caption=None,
            chat_id=11,
            from_user=SimpleNamespace(id=123, username="owner", first_name="Owner", language_code="en"),
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
            from_user=SimpleNamespace(id=999, username="guest", first_name="Guest", language_code="en"),
            message_id=11,
            chat=SimpleNamespace(type="private"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        await channel._handle_update(
            SimpleNamespace(update_id=101, message=allowed_message, edited_message=None, effective_message=allowed_message)
        )
        await channel._handle_update(
            SimpleNamespace(update_id=102, message=blocked_message, edited_message=None, effective_message=blocked_message)
        )

        assert len(emitted) == 1
        assert emitted[0][1] == "123"
        signals = channel.signals()
        assert signals["policy_allowed_count"] == 1
        assert signals["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_group_policy_disabled_blocks_group_message() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "group_policy": "disabled"},
            on_message=_on_message,
        )
        message = SimpleNamespace(
            text="group",
            caption=None,
            chat_id=-1001,
            from_user=SimpleNamespace(id=55, username="alice", first_name="Alice", language_code="en"),
            message_id=10,
            chat=SimpleNamespace(type="group"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        processed = await channel._handle_update(
            SimpleNamespace(update_id=103, message=message, edited_message=None, effective_message=message)
        )

        assert processed is True
        assert emitted == []
        assert channel.signals()["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_topic_allowlist_policy_allows_listed_thread_user_and_blocks_nonlisted() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "topic_policy": "allowlist", "topic_allow_from": ["@alice"]},
            on_message=_on_message,
        )
        allowed_message = SimpleNamespace(
            text="thread allowed",
            caption=None,
            chat_id=-1002,
            message_thread_id=7,
            from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en"),
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
            from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="en"),
            message_id=21,
            chat=SimpleNamespace(type="supergroup"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        await channel._handle_update(
            SimpleNamespace(update_id=104, message=allowed_message, edited_message=None, effective_message=allowed_message)
        )
        await channel._handle_update(
            SimpleNamespace(update_id=105, message=blocked_message, edited_message=None, effective_message=blocked_message)
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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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
            from_user=SimpleNamespace(id=22, username="guest", first_name="Guest", language_code="en"),
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
            from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en"),
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
            from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="en"),
            message_id=33,
            chat=SimpleNamespace(type="supergroup"),
            date=None,
            edit_date=None,
            reply_to_message=None,
        )

        await channel._handle_update(
            SimpleNamespace(update_id=106, message=group_message, edited_message=None, effective_message=group_message)
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
        assert [entry[2] for entry in emitted] == ["group override open", "topic allowed"]
        signals = channel.signals()
        assert signals["policy_allowed_count"] == 2
        assert signals["policy_blocked_count"] == 1

    asyncio.run(_scenario())


def test_telegram_callback_query_policy_blocked_when_context_denies() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(
            config={"token": "x:token", "reaction_notifications": "all", "group_policy": "disabled"},
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


def test_telegram_drop_pending_updates_on_startup() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token", "drop_pending_updates": True})
        channel._save_offset = lambda: None  # type: ignore[method-assign]

        class FakeBot:
            def __init__(self) -> None:
                self.calls = 0

            async def get_updates(self, *, offset, timeout, allowed_updates):
                self.calls += 1
                if self.calls == 1:
                    return [SimpleNamespace(update_id=12), SimpleNamespace(update_id=13)]
                return []

        channel.bot = FakeBot()
        channel._offset = 0
        await channel._drop_pending_updates()

        assert channel._offset == 14

    asyncio.run(_scenario())


def test_telegram_command_help_is_handled_locally() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        class FakeBot:
            def __init__(self) -> None:
                self.sent: list[dict] = []

            async def send_message(self, **kwargs):
                self.sent.append(kwargs)

        bot = FakeBot()
        channel.bot = bot

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

        await channel._handle_update(update)

        assert len(bot.sent) == 1
        assert "ClawLite commands" in bot.sent[0]["text"]
        assert emitted == []

    asyncio.run(_scenario())


def test_telegram_command_stop_is_forwarded_with_metadata() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

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


def test_telegram_edited_message_duplicate_is_deduped() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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

        update_message = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)
        update_edit = SimpleNamespace(update_id=101, message=None, edited_message=edited_same, effective_message=edited_same)

        await channel._handle_update(update_message)
        await channel._handle_update(update_edit)

        assert len(emitted) == 1
        assert emitted[0][2] == "hello"
        assert emitted[0][3]["is_edit"] is False

    asyncio.run(_scenario())


def test_telegram_reply_metadata_is_emitted() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
        reply_user = SimpleNamespace(id=9, username="bob")
        reply_to = SimpleNamespace(message_id=3, text="parent", caption=None, from_user=reply_user)
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, text
            emitted.append(metadata)

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

        await channel._handle_update(update)

        assert len(emitted) == 1
        assert emitted[0]["message_thread_id"] == 7

    asyncio.run(_scenario())


def test_telegram_media_only_message_is_forwarded_with_placeholder() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=101, message=message, edited_message=None, effective_message=message)

        await channel._handle_update(update)

        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "telegram:42"
        assert user_id == "1"
        assert text == "[telegram media message: photo(2), voice]"
        assert metadata["media_present"] is True
        assert metadata["media_types"] == ["photo", "voice"]
        assert metadata["media_counts"] == {"photo": 2, "voice": 1}
        assert metadata["media_total_count"] == 3

    asyncio.run(_scenario())


def test_telegram_callback_query_is_forwarded_and_acknowledged() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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


def test_telegram_callback_query_blocked_by_allowlist_does_not_emit() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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

        out = await channel.send(target="42", text="hello", metadata={"message_thread_id": 13})

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


def test_telegram_send_retries_without_thread_kwarg_on_old_library() -> None:
    async def _scenario() -> None:
        channel = TelegramChannel(config={"token": "x:token"})

        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def send_message(self, **kwargs):
                self.calls.append(kwargs)
                if "message_thread_id" in kwargs:
                    raise TypeError("got an unexpected keyword argument 'message_thread_id'")
                return True

        bot = FakeBot()
        channel.bot = bot

        out = await channel.send(target="42:5", text="hello")

        assert out == "telegram:sent:1"
        assert len(bot.calls) == 2
        assert "message_thread_id" in bot.calls[0]
        assert "message_thread_id" not in bot.calls[1]

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


def test_telegram_offset_commits_after_successful_processing() -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(config={"token": "x:token", "poll_interval_s": 0.01}, on_message=_on_message)
        saved: list[int] = []
        channel._save_offset = lambda: saved.append(channel._offset)  # type: ignore[method-assign]

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

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
        assert saved[-1] == 101

    asyncio.run(_scenario())


def test_telegram_offset_not_committed_when_processing_fails() -> None:
    async def _scenario() -> None:
        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, text, metadata
            channel._running = False
            raise RuntimeError("boom")

        channel = TelegramChannel(config={"token": "x:token", "poll_interval_s": 0.01}, on_message=_on_message)
        saved: list[int] = []
        channel._save_offset = lambda: saved.append(channel._offset)  # type: ignore[method-assign]

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

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
        assert saved == []

    asyncio.run(_scenario())


def test_telegram_polling_transient_failure_recovers_and_processes_update() -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, metadata
            emitted.append(text)
            channel._running = False

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "reconnect_initial_s": 0.01,
                "reconnect_max_s": 0.01,
            },
            on_message=_on_message,
        )
        channel._save_offset = lambda: None  # type: ignore[method-assign]

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

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
        with patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()), patch.dict(
            sys.modules, {"telegram": fake_module}
        ):
            await channel._poll_loop()

        assert emitted == ["hello"]
        assert channel._offset == 101
        assert channel.signals()["reconnect_count"] >= 1

    asyncio.run(_scenario())


def test_telegram_polling_soak_recovery_reconnects_then_stabilizes() -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "reconnect_initial_s": 0.01,
                "reconnect_max_s": 0.02,
            },
            on_message=_on_message,
        )
        channel._save_offset = lambda: None  # type: ignore[method-assign]

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

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
        with patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()), patch.dict(
            sys.modules, {"telegram": fake_module}
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


def test_telegram_redelivery_reprocesses_after_failed_emit_then_commits_offset() -> None:
    async def _scenario() -> None:
        emitted: list[str] = []
        attempts = 0

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, metadata
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("boom")
            emitted.append(text)

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
        saved: list[int] = []
        channel._save_offset = lambda: saved.append(channel._offset)  # type: ignore[method-assign]

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

        try:
            await channel._handle_update(update)
            raise AssertionError("expected first emit failure")
        except RuntimeError:
            pass

        assert attempts == 1
        assert emitted == []
        assert channel._offset == 0
        assert saved == []

        processed_ok = await channel._handle_update(update)
        assert processed_ok is True
        channel._offset = max(channel._offset, int(update.update_id) + 1)
        channel._save_offset()

        assert attempts == 2
        assert emitted == ["hello"]
        assert channel._offset == 101
        assert saved == [101]

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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, text, metadata
            await asyncio.wait_for(typing_started.wait(), timeout=1.0)
            await channel.send(target="42", text="response")

        channel.on_message = _on_message

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
        update = SimpleNamespace(update_id=100, message=message, edited_message=None, effective_message=message)

        await channel._handle_update(update)

        assert bot.typing_calls >= 1
        assert bot.send_calls == 1
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


def test_telegram_polling_recovery_matrix_multiple_reconnects_then_stable_updates() -> None:
    async def _scenario() -> None:
        emitted: list[str] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
            del session_id, user_id, metadata
            emitted.append(text)

        channel = TelegramChannel(
            config={
                "token": "x:token",
                "poll_interval_s": 0.01,
                "reconnect_initial_s": 0.01,
                "reconnect_max_s": 0.02,
            },
            on_message=_on_message,
        )
        saved_offsets: list[int] = []
        channel._save_offset = lambda: saved_offsets.append(channel._offset)  # type: ignore[method-assign]

        user = SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="en")
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
            return SimpleNamespace(update_id=update_id, message=msg, edited_message=None, effective_message=msg)

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

        bot_factory = Mock(side_effect=[FailingBot(), FailingBot(), FailingBot(), StableBot()])
        fake_module = SimpleNamespace(Bot=bot_factory)

        channel._running = True
        with patch("clawlite.channels.telegram.asyncio.sleep", new=AsyncMock()), patch.dict(
            sys.modules, {"telegram": fake_module}
        ):
            await channel._poll_loop()

        signals = channel.signals()
        assert emitted == ["u100", "u101", "u102"]
        assert channel._offset == 103
        assert saved_offsets == [101, 102, 103]
        assert channel._connected is True
        assert signals["reconnect_count"] == 3
        assert signals["send_auth_breaker_open"] is False
        assert signals["typing_auth_breaker_open"] is False

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
                "callback_query",
                "message_reaction",
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


def test_telegram_handle_webhook_update_normalizes_callback_payload_and_dedupes() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict[str, object]) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)

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


def test_telegram_channel_post_is_forwarded() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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


def test_telegram_handle_webhook_update_normalizes_channel_post_payload() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, object]]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict[str, object]) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = TelegramChannel(config={"token": "x:token"}, on_message=_on_message)
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


def test_telegram_message_reaction_notifications_all_emits_event() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict]] = []

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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

        async def _on_message(session_id: str, user_id: str, text: str, metadata: dict) -> None:
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
