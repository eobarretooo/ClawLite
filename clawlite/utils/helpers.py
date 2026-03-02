from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def chunk_text(text: str, max_len: int = 4000) -> list[str]:
    if max_len <= 0:
        raise ValueError("max_len must be > 0")
    content = str(text or "")
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    start = 0
    while start < len(content):
        chunks.append(content[start : start + max_len])
        start += max_len
    return chunks
