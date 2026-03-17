from __future__ import annotations

import json
import os
import time
from urllib.parse import quote, unquote
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

    def __init__(
        self,
        root: str | Path | None = None,
        max_messages_per_session: int | None = 2000,
        session_retention_ttl_s: float | int | None = None,
    ) -> None:
        base = Path(root) if root else (Path.home() / ".clawlite" / "state" / "sessions")
        self.root = base
        self.root.mkdir(parents=True, exist_ok=True)
        configured_limit = None if max_messages_per_session is None else int(max_messages_per_session)
        self.max_messages_per_session = configured_limit if configured_limit and configured_limit > 0 else None
        configured_ttl = None if session_retention_ttl_s is None else float(session_retention_ttl_s)
        self.session_retention_ttl_s = configured_ttl if configured_ttl and configured_ttl > 0 else None
        self._strict_compaction_limit = 64
        self._session_line_estimates: dict[Path, int] = {}
        self._diagnostics: dict[str, int | str] = {
            "append_attempts": 0,
            "append_retries": 0,
            "append_failures": 0,
            "append_success": 0,
            "compaction_runs": 0,
            "compaction_trimmed_lines": 0,
            "compaction_failures": 0,
            "read_corrupt_lines": 0,
            "read_repaired_files": 0,
            "ttl_prune_runs": 0,
            "ttl_prune_deleted_sessions": 0,
            "ttl_prune_failures": 0,
            "ttl_last_prune_iso": "",
            "last_error": "",
        }

    def _safe_session_id(self, session_id: str) -> str:
        clean = str(session_id or "").strip()
        return quote(clean, safe="-_.").strip("_")

    @staticmethod
    def _legacy_safe_session_id(session_id: str) -> str:
        return "".join(
            ch if ch.isalnum() or ch in {"-", "_", ":"} else "_"
            for ch in str(session_id or "")
        ).strip("_")

    @staticmethod
    def _restore_session_id(stem: str) -> str:
        return unquote(str(stem or "").strip())

    def _path(self, session_id: str) -> Path:
        sid = self._safe_session_id(str(session_id or "").strip())
        if not sid:
            raise ValueError("session_id is required")
        encoded_path = self.root / f"{sid}.jsonl"
        legacy_sid = self._legacy_safe_session_id(str(session_id or "").strip())
        legacy_path = self.root / f"{legacy_sid}.jsonl"
        if encoded_path.exists():
            return encoded_path
        if legacy_path != encoded_path and legacy_path.exists():
            return legacy_path
        return encoded_path

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
                cached_count = self._session_line_estimates.get(path)
                if cached_count is None:
                    self._session_line_estimates[path] = self._get_line_estimate(path)
                else:
                    self._session_line_estimates[path] = cached_count + 1
                self._maybe_compact_session_file(path)
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
            self._atomic_rewrite(path, rewritten)
            self._diagnostics["read_repaired_files"] = int(self._diagnostics["read_repaired_files"]) + 1
            self._session_line_estimates.pop(path, None)
            self._diagnostics["last_error"] = ""
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

    def _get_line_estimate(self, path: Path) -> int:
        cached = self._session_line_estimates.get(path)
        if cached is not None:
            return cached
        if not path.exists():
            self._session_line_estimates[path] = 0
            return 0
        count = 0
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                continue
            count += 1
        self._session_line_estimates[path] = count
        return count

    @staticmethod
    def _overflow_budget(limit: int) -> int:
        return max(1, limit // 10)

    def _maybe_compact_session_file(self, path: Path) -> None:
        limit = self.max_messages_per_session
        if limit is None:
            return
        if limit <= self._strict_compaction_limit:
            new_count = self._compact_session_file(path)
            if new_count is not None:
                self._session_line_estimates[path] = new_count
            return

        estimated_count = self._get_line_estimate(path)
        overflow = estimated_count - limit
        if overflow < self._overflow_budget(limit):
            return

        new_count = self._compact_session_file(path)
        if new_count is not None:
            self._session_line_estimates[path] = new_count

    def _atomic_rewrite(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            dir_fd = -1
            try:
                dir_fd = os.open(str(path.parent), os.O_RDONLY)
                os.fsync(dir_fd)
            except OSError:
                pass
            finally:
                if dir_fd >= 0:
                    os.close(dir_fd)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _compact_session_file(self, path: Path) -> int | None:
        limit = self.max_messages_per_session
        if limit is None:
            return None
        self._diagnostics["compaction_runs"] = int(self._diagnostics["compaction_runs"]) + 1
        try:
            valid_lines: list[str] = []
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                raw = line.strip()
                if not raw:
                    continue
                try:
                    json.loads(raw)
                except json.JSONDecodeError:
                    continue
                valid_lines.append(raw)

            keep = valid_lines[-limit:]
            trimmed = max(0, len(valid_lines) - len(keep))
            rewritten = "\n".join(keep)
            if rewritten:
                rewritten = f"{rewritten}\n"
            self._atomic_rewrite(path, rewritten)
            if trimmed:
                self._diagnostics["compaction_trimmed_lines"] = int(self._diagnostics["compaction_trimmed_lines"]) + trimmed
            self._diagnostics["last_error"] = ""
            return len(keep)
        except Exception as exc:
            self._diagnostics["compaction_failures"] = int(self._diagnostics["compaction_failures"]) + 1
            self._diagnostics["last_error"] = str(exc)
            return None

    def diagnostics(self) -> dict[str, int | str]:
        return {
            "append_attempts": int(self._diagnostics["append_attempts"]),
            "append_retries": int(self._diagnostics["append_retries"]),
            "append_failures": int(self._diagnostics["append_failures"]),
            "append_success": int(self._diagnostics["append_success"]),
            "compaction_runs": int(self._diagnostics["compaction_runs"]),
            "compaction_trimmed_lines": int(self._diagnostics["compaction_trimmed_lines"]),
            "compaction_failures": int(self._diagnostics["compaction_failures"]),
            "read_corrupt_lines": int(self._diagnostics["read_corrupt_lines"]),
            "read_repaired_files": int(self._diagnostics["read_repaired_files"]),
            "session_retention_ttl_s": (
                None if self.session_retention_ttl_s is None else float(self.session_retention_ttl_s)
            ),
            "ttl_prune_runs": int(self._diagnostics["ttl_prune_runs"]),
            "ttl_prune_deleted_sessions": int(self._diagnostics["ttl_prune_deleted_sessions"]),
            "ttl_prune_failures": int(self._diagnostics["ttl_prune_failures"]),
            "ttl_last_prune_iso": str(self._diagnostics["ttl_last_prune_iso"]),
            "last_error": str(self._diagnostics["last_error"]),
        }

    def list_sessions(self) -> list[str]:
        return sorted(self._restore_session_id(path.stem) for path in self.root.glob("*.jsonl"))

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def prune_expired(self, *, now: float | None = None, max_age_seconds: float | None = None) -> int:
        ttl_s = self.session_retention_ttl_s if max_age_seconds is None else float(max_age_seconds)
        if ttl_s is None or ttl_s <= 0:
            return 0
        current_time = time.time() if now is None else float(now)
        deleted = 0
        self._diagnostics["ttl_prune_runs"] = int(self._diagnostics["ttl_prune_runs"]) + 1
        self._diagnostics["ttl_last_prune_iso"] = _utc_now()
        for path in self.root.glob("*.jsonl"):
            try:
                modified_at = path.stat().st_mtime
            except OSError as exc:
                self._diagnostics["ttl_prune_failures"] = int(self._diagnostics["ttl_prune_failures"]) + 1
                self._diagnostics["last_error"] = str(exc)
                continue
            age_seconds = max(0.0, current_time - float(modified_at))
            if age_seconds <= ttl_s:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                self._diagnostics["ttl_prune_failures"] = int(self._diagnostics["ttl_prune_failures"]) + 1
                self._diagnostics["last_error"] = str(exc)
                continue
            self._session_line_estimates.pop(path, None)
            deleted += 1
        if deleted:
            self._diagnostics["ttl_prune_deleted_sessions"] = int(
                self._diagnostics["ttl_prune_deleted_sessions"]
            ) + deleted
        if deleted or int(self._diagnostics["ttl_prune_failures"]) == 0:
            self._diagnostics["last_error"] = ""
        return deleted
