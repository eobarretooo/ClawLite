from __future__ import annotations

from pathlib import Path

from clawlite.utils.helpers import chunk_text, ensure_dir


def test_chunk_text_splits() -> None:
    chunks = chunk_text("abcdef", max_len=2)
    assert chunks == ["ab", "cd", "ef"]


def test_ensure_dir_creates_path(tmp_path: Path) -> None:
    created = ensure_dir(tmp_path / "a" / "b")
    assert created.exists()
    assert created.is_dir()
