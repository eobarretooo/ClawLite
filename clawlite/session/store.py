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
        metadata_payload = dict(metadata or {})
        if clean_role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("invalid role")
        if not clean_content and not self._metadata_allows_empty_content(metadata_payload):
            return

        msg = SessionMessage(
            session_id=str(session_id),
            role=clean_role,
            content=clean_content,
            metadata=metadata_payload,
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

    def append_many(
        self,
        session_id: str,
        rows: list[dict[str, Any]],
    ) -> None:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            raise ValueError("session_id is required")
        messages: list[SessionMessage] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            clean_role = str(row.get("role", "") or "").strip().lower()
            clean_content = str(row.get("content", "") or "").strip()
            metadata_payload = dict(row.get("metadata") or {})
            if clean_role not in {"system", "user", "assistant", "tool"}:
                raise ValueError("invalid role")
            if not clean_content and not self._metadata_allows_empty_content(metadata_payload):
                continue
            messages.append(
                SessionMessage(
                    session_id=clean_session_id,
                    role=clean_role,
                    content=clean_content,
                    metadata=metadata_payload,
                )
            )
        if not messages:
            return

        path = self._path(clean_session_id)
        payload = "".join(json.dumps(asdict(msg), ensure_ascii=False) + "\n" for msg in messages)
        attempts = 2
        for attempt in range(1, attempts + 1):
            self._diagnostics["append_attempts"] = int(self._diagnostics["append_attempts"]) + 1
            try:
                self._append_once(path, payload)
                self._diagnostics["append_success"] = int(self._diagnostics["append_success"]) + len(messages)
                self._diagnostics["last_error"] = ""
                cached_count = self._session_line_estimates.get(path)
                if cached_count is None:
                    self._session_line_estimates[path] = self._get_line_estimate(path)
                else:
                    self._session_line_estimates[path] = cached_count + len(messages)
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
        rows = self.read_messages(session_id, limit=limit)
        simplified: list[dict[str, str]] = []
        for row in rows:
            role = str(row.get("role", "")).strip()
            content = str(row.get("content", "")).strip()
            if not role or not content:
                continue
            simplified.append({"role": role, "content": content})
        return simplified

    @staticmethod
    def _metadata_allows_empty_content(metadata: dict[str, Any]) -> bool:
        if not isinstance(metadata, dict) or not metadata:
            return False
        tool_calls = metadata.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            return True
        return bool(str(metadata.get("tool_call_id", "")).strip())

    @staticmethod
    def _normalize_tool_calls(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            call_id = str(item.get("id", "")).strip()
            function = item.get("function")
            if not call_id or not isinstance(function, dict):
                continue
            name = str(function.get("name", "")).strip()
            arguments = function.get("arguments", "{}")
            if not name:
                continue
            rows.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": str(arguments or "{}"),
                    },
                }
            )
        return rows

    @classmethod
    def _payload_to_message_row(cls, payload: dict[str, Any]) -> dict[str, Any] | None:
        role = str(payload.get("role", "")).strip()
        content = str(payload.get("content", "") or "").strip()
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        if role not in {"system", "user", "assistant", "tool"}:
            return None

        row: dict[str, Any] = {"role": role, "content": content}
        if role == "assistant":
            tool_calls = cls._normalize_tool_calls(
                metadata.get("tool_calls", payload.get("tool_calls"))
            )
            if tool_calls:
                row["tool_calls"] = tool_calls
        elif role == "tool":
            tool_call_id = str(
                metadata.get("tool_call_id", payload.get("tool_call_id", "")) or ""
            ).strip()
            tool_name = str(metadata.get("name", payload.get("name", "")) or "").strip()
            if tool_call_id:
                row["tool_call_id"] = tool_call_id
            if tool_name:
                row["name"] = tool_name

        if not str(row.get("content", "")).strip() and not cls._metadata_allows_empty_content(metadata):
            return None
        return row

    @classmethod
    def _filter_assistant_tool_calls(
        cls,
        row: dict[str, Any],
        *,
        allowed_ids: set[str],
    ) -> dict[str, Any] | None:
        raw_tool_calls = row.get("tool_calls")
        if not isinstance(raw_tool_calls, list):
            return None
        filtered = [
            item
            for item in raw_tool_calls
            if isinstance(item, dict) and str(item.get("id", "")).strip() in allowed_ids
        ]
        if not filtered:
            return None
        updated = dict(row)
        updated["tool_calls"] = filtered
        return updated

    @classmethod
    def _legalize_transcript_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        pending_assistant: dict[str, Any] | None = None
        pending_allowed_ids: set[str] = set()
        pending_results: list[dict[str, Any]] = []

        def flush_pending() -> None:
            nonlocal pending_assistant, pending_allowed_ids, pending_results
            if pending_assistant and pending_results:
                realized_ids = {
                    str(item.get("tool_call_id", "")).strip()
                    for item in pending_results
                    if str(item.get("tool_call_id", "")).strip()
                }
                filtered_assistant = cls._filter_assistant_tool_calls(
                    pending_assistant,
                    allowed_ids=realized_ids,
                )
                if filtered_assistant is not None:
                    out.append(filtered_assistant)
                    out.extend(pending_results)
            pending_assistant = None
            pending_allowed_ids = set()
            pending_results = []

        for row in rows:
            role = str(row.get("role", "")).strip()
            tool_calls = row.get("tool_calls")
            if role == "assistant" and isinstance(tool_calls, list) and tool_calls:
                flush_pending()
                pending_assistant = dict(row)
                pending_allowed_ids = {
                    str(item.get("id", "")).strip()
                    for item in tool_calls
                    if isinstance(item, dict) and str(item.get("id", "")).strip()
                }
                pending_results = []
                continue

            if role == "tool":
                tool_call_id = str(row.get("tool_call_id", "")).strip()
                if pending_assistant and tool_call_id and tool_call_id in pending_allowed_ids:
                    pending_results.append(dict(row))
                continue

            flush_pending()
            out.append(dict(row))

        flush_pending()
        return out

    def read_messages(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        path = self._path(session_id)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
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
            if not isinstance(payload, dict):
                continue
            row = self._payload_to_message_row(payload)
            if row is not None:
                rows.append(row)

        if corrupt_lines:
            self._diagnostics["read_corrupt_lines"] = int(self._diagnostics["read_corrupt_lines"]) + corrupt_lines
            self._repair_file(path, valid_lines)

        legalized = self._legalize_transcript_rows(rows)
        return legalized[-max(1, int(limit or 1)) :]

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

        estimated_count = self._session_line_estimates.get(path)
        if estimated_count is None:
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
        ranked: list[tuple[float, str]] = []
        for path in self.root.glob("*.jsonl"):
            try:
                modified_at = float(path.stat().st_mtime)
            except OSError:
                modified_at = 0.0
            ranked.append((modified_at, self._restore_session_id(path.stem)))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [session_id for _mtime, session_id in ranked]

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
