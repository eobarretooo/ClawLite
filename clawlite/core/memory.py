from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover
    BM25Okapi = None

WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


@dataclass(slots=True)
class MemoryRecord:
    id: str
    text: str
    source: str
    created_at: str


class MemoryStore:
    """Simple JSONL long-term memory with BM25 retrieval."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.path = Path(db_path) if db_path else (Path.home() / ".clawlite" / "state" / "memory.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [m.group(0).lower() for m in WORD_RE.finditer(text)]

    def add(self, text: str, *, source: str = "user") -> MemoryRecord:
        clean = text.strip()
        if not clean:
            raise ValueError("memory text must not be empty")
        row = MemoryRecord(
            id=uuid.uuid4().hex,
            text=clean,
            source=source,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        return row

    def all(self) -> list[MemoryRecord]:
        out: list[MemoryRecord] = []
        for line in self.path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(
                MemoryRecord(
                    id=str(payload.get("id", "")),
                    text=str(payload.get("text", "")).strip(),
                    source=str(payload.get("source", "unknown")),
                    created_at=str(payload.get("created_at", "")),
                )
            )
        return [item for item in out if item.text]

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        records = self.all()
        if not records:
            return []

        q_tokens = self._tokens(query)
        if not q_tokens:
            return records[-limit:][::-1]

        corpus_tokens = [self._tokens(item.text) for item in records]

        if BM25Okapi is None:
            # Fallback lexical score if rank_bm25 is missing.
            scored = []
            qset = set(q_tokens)
            for idx, toks in enumerate(corpus_tokens):
                overlap = len(qset.intersection(toks))
                scored.append((float(overlap), idx))
        else:
            bm25 = BM25Okapi(corpus_tokens)
            scores = bm25.get_scores(q_tokens)
            scored = [(float(scores[idx]), idx) for idx in range(len(records))]

        scored.sort(key=lambda item: item[0], reverse=True)

        picked: list[MemoryRecord] = []
        for score, idx in scored:
            if len(picked) >= limit:
                break
            if math.isclose(score, 0.0):
                continue
            picked.append(records[idx])

        return picked if picked else records[-limit:][::-1]

    def consolidate(self, messages: Iterable[dict[str, str]], *, source: str = "session") -> MemoryRecord | None:
        lines: list[str] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        if not lines:
            return None
        summary = "\n".join(lines[-12:])
        return self.add(summary, source=source)


# Backward-compatible API expected by legacy CLI.
def add_note(text: str) -> None:
    MemoryStore().add(text, source="legacy")


def search_notes(query: str, limit: int = 10) -> list[str]:
    return [row.text for row in MemoryStore().search(query, limit=limit)]
