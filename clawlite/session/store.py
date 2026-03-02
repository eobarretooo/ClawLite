from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SessionMessage:
    session_id: str
    role: str
    content: str
    ts: str = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    """
    JSONL-backed session storage.

    Each session is persisted in its own file:
    ~/.clawlite/state/sessions/<session_id>.jsonl
    """

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root else (Path.home() / ".clawlite" / "state" / "sessions")
        self.root = base
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_session_id(self, session_id: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_", ":"} else "_" for ch in session_id).strip("_")

    def _path(self, session_id: str) -> Path:
        sid = self._safe_session_id(str(session_id or "").strip())
        if not sid:
            raise ValueError("session_id is required")
        return self.root / f"{sid}.jsonl"

    def append(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        clean_role = str(role or "").strip().lower()
        clean_content = str(content or "").strip()
        if clean_role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("invalid role")
        if not clean_content:
            return

        msg = SessionMessage(
            session_id=str(session_id),
            role=clean_role,
            content=clean_content,
            metadata=dict(metadata or {}),
        )
        path = self._path(msg.session_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(msg), ensure_ascii=False) + "\n")

    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        path = self._path(session_id)
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            role = str(payload.get("role", "")).strip()
            content = str(payload.get("content", "")).strip()
            if not role or not content:
                continue
            rows.append({"role": role, "content": content})
        return rows[-max(1, int(limit or 1)) :]

    def list_sessions(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.jsonl"))

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True
