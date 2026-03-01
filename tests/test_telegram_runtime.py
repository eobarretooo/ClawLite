from __future__ import annotations

from pathlib import Path

from clawlite.channels.telegram_runtime import (
    TelegramUpdateOffsetStore,
    chunk_telegram_text,
)


def test_chunk_telegram_text_respects_limit() -> None:
    text = "linha 1\n" + ("x" * 4500) + "\nlinha 2"
    chunks = chunk_telegram_text(text, limit=4000)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") != ""


def test_chunk_telegram_text_preserves_short_message() -> None:
    text = "mensagem curta"
    chunks = chunk_telegram_text(text, limit=4000)
    assert chunks == [text]


def test_offset_store_roundtrip(tmp_path: Path) -> None:
    store = TelegramUpdateOffsetStore(
        token="12345:token",
        account_id="default",
        root_dir=tmp_path,
    )
    assert store.read() is None
    store.write(42)
    assert store.read() == 42


def test_offset_store_ignores_other_bot_id(tmp_path: Path) -> None:
    shared_dir = tmp_path / "state"
    store_a = TelegramUpdateOffsetStore(
        token="11111:a",
        account_id="acc",
        root_dir=shared_dir,
    )
    store_b = TelegramUpdateOffsetStore(
        token="22222:b",
        account_id="acc",
        root_dir=shared_dir,
    )
    store_a.write(99)
    assert store_b.read() is None
