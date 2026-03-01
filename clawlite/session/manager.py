from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from clawlite.config import settings as app_settings


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """Armazena e consulta histórico de sessões em JSONL."""

    def __init__(self, path: Path | None = None) -> None:
        if path is not None:
            self.path = Path(path)
        else:
            self.path = Path(app_settings.CONFIG_DIR) / "dashboard" / "sessions.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        session_id: str,
        role: str,
        text: str,
        ts: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        sid = str(session_id or "").strip()
        msg = str(text or "").strip()
        r = str(role or "").strip().lower()
        if not sid or not msg or r not in {"system", "user", "assistant"}:
            return

        row: dict[str, Any] = {
            "ts": str(ts or _iso_now()),
            "session_id": sid,
            "role": r,
            "text": msg,
        }
        if isinstance(extra, dict):
            for key, value in extra.items():
                if key in row:
                    continue
                row[key] = value

        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return iter(())
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return iter(rows)

    def recent(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        sid = str(session_id or "").strip()
        if not sid:
            return []
        rows = [row for row in self.iter_rows() if str(row.get("session_id", "")) == sid]
        if limit <= 0:
            return rows
        return rows[-limit:]

