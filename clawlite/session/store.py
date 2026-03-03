from __future__ import annotations

import json
import os
import time
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
        self._diagnostics: dict[str, int | str] = {
            "append_attempts": 0,
            "append_retries": 0,
            "append_failures": 0,
            "append_success": 0,
            "read_corrupt_lines": 0,
            "read_repaired_files": 0,
            "last_error": "",
        }

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
        payload = json.dumps(asdict(msg), ensure_ascii=False) + "\n"

        attempts = 2
        for attempt in range(1, attempts + 1):
            self._diagnostics["append_attempts"] = int(self._diagnostics["append_attempts"]) + 1
            try:
                self._append_once(path, payload)
                self._diagnostics["append_success"] = int(self._diagnostics["append_success"]) + 1
                self._diagnostics["last_error"] = ""
                return
            except OSError as exc:
                self._diagnostics["last_error"] = str(exc)
                if attempt < attempts:
                    self._diagnostics["append_retries"] = int(self._diagnostics["append_retries"]) + 1
                    time.sleep(0.01)
                    continue
                self._diagnostics["append_failures"] = int(self._diagnostics["append_failures"]) + 1
                raise

    @staticmethod
    def _append_once(path: Path, payload: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def read(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        path = self._path(session_id)
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        valid_lines: list[str] = []
        corrupt_lines = 0
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                corrupt_lines += 1
                continue
            valid_lines.append(raw)
            role = str(payload.get("role", "")).strip()
            content = str(payload.get("content", "")).strip()
            if not role or not content:
                continue
            rows.append({"role": role, "content": content})

        if corrupt_lines:
            self._diagnostics["read_corrupt_lines"] = int(self._diagnostics["read_corrupt_lines"]) + corrupt_lines
            self._repair_file(path, valid_lines)

        return rows[-max(1, int(limit or 1)) :]

    def _repair_file(self, path: Path, valid_lines: list[str]) -> None:
        try:
            rewritten = "\n".join(valid_lines)
            if rewritten:
                rewritten = f"{rewritten}\n"
            path.write_text(rewritten, encoding="utf-8")
            self._diagnostics["read_repaired_files"] = int(self._diagnostics["read_repaired_files"]) + 1
            self._diagnostics["last_error"] = ""
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

    def diagnostics(self) -> dict[str, int | str]:
        return {
            "append_attempts": int(self._diagnostics["append_attempts"]),
            "append_retries": int(self._diagnostics["append_retries"]),
            "append_failures": int(self._diagnostics["append_failures"]),
            "append_success": int(self._diagnostics["append_success"]),
            "read_corrupt_lines": int(self._diagnostics["read_corrupt_lines"]),
            "read_repaired_files": int(self._diagnostics["read_repaired_files"]),
            "last_error": str(self._diagnostics["last_error"]),
        }

    def list_sessions(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.jsonl"))

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True
