from __future__ import annotations

from clawlite.channels.telegram import split_message


def test_telegram_split_message_chunking() -> None:
    text = "a" * 9000
    chunks = split_message(text, max_len=4000)
    assert len(chunks) == 3
    assert sum(len(c) for c in chunks) == 9000
    assert all(len(c) <= 4000 for c in chunks)
