from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MemoryBackend(Protocol):
    """Optional memory backend contract for runtime selection."""

    @property
    def name(self) -> str:
        ...

    def is_supported(self) -> bool:
        ...


@dataclass(slots=True)
class SQLiteMemoryBackend:
    @property
    def name(self) -> str:
        return "sqlite"

    def is_supported(self) -> bool:
        return True


@dataclass(slots=True)
class PgvectorMemoryBackend:
    pgvector_url: str = ""

    @property
    def name(self) -> str:
        return "pgvector"

    def is_supported(self) -> bool:
        url = str(self.pgvector_url or "").strip().lower()
        if not url:
            return False
        return url.startswith("postgres://") or url.startswith("postgresql://")


def resolve_memory_backend(backend_name: str, pgvector_url: str = "") -> MemoryBackend:
    normalized = str(backend_name or "sqlite").strip().lower()
    if normalized == "pgvector":
        return PgvectorMemoryBackend(pgvector_url=str(pgvector_url or ""))
    return SQLiteMemoryBackend()
