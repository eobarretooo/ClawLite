from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
