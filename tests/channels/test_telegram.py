from __future__ import annotations

from clawlite.channels.telegram import split_message
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
