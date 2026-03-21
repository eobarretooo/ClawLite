from __future__ import annotations

import asyncio
import json
import hashlib
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from clawlite.core.memory import MemoryRecord, MemoryStore


@dataclass(slots=True)
class MemorySuggestion:
    text: str
    priority: float
    trigger: str
    channel: str
    target: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = self.suggestion_id
        payload["semantic_key"] = self.semantic_key
        if not payload.get("created_at"):
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        return payload

    @property
    def suggestion_id(self) -> str:
        base = f"{self.semantic_key}|{self.text}".strip().lower()
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    @property
    def semantic_key(self) -> str:
        identity_fields = ("record_id", "topic", "month_day", "event_date", "event_kind", "legacy_trigger")
        identity: dict[str, Any] = {}
        for key in identity_fields:
            if key in self.metadata:
                identity[key] = self.metadata[key]
        if not identity:
            identity = {
                str(k): self.metadata[k]
                for k in sorted(self.metadata.keys())
                if not str(k).startswith("_")
            }
        canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        base = f"{self.trigger}|{self.channel}|{self.target}|{canonical}".strip().lower()
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


class MemoryMonitor:
    _DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
    _MONTH_DAY_RE = re.compile(r"\b(\d{2})[-/](\d{2})\b")
    _TASK_RE = re.compile(r"\b(todo|pendente|pending|task|tarefa|fazer)\b", re.IGNORECASE)
    _DONE_RE = re.compile(r"\b(done|feito|concluido|concluído|resolved|resolvido)\b", re.IGNORECASE)
    _BIRTHDAY_RE = re.compile(r"\b(birthday|aniversario|aniversário)\b", re.IGNORECASE)
    _TRAVEL_RE = re.compile(r"\b(travel|trip|viagem|voo|flight)\b", re.IGNORECASE)

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        suggestions_path: str | Path | None = None,
        cooldown_seconds: float = 3600.0,
        retry_backoff_seconds: float = 300.0,
        max_retry_attempts: int = 3,
    ) -> None:
        self.store = store or MemoryStore()
        self.suggestions_path = Path(suggestions_path) if suggestions_path else (self.store.memory_home / "suggestions_pending.json")
        self.cooldown_seconds = max(0.0, float(cooldown_seconds or 0.0))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds or 0.0))
        self.max_retry_attempts = max(1, int(max_retry_attempts or 1))
        self._telemetry: dict[str, int] = {
            "scans": 0,
            "generated": 0,
            "deduped": 0,
            "low_priority_skipped": 0,
            "cooldown_skipped": 0,
            "sent": 0,
            "failed": 0,
        }
        self._pending_lock = threading.Lock()
        self.suggestions_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.suggestions_path.exists():
            self._atomic_write_pending_text("[]\n")

    @staticmethod
    def _flush_and_fsync(handle: Any) -> None:
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except Exception:
            pass

    def _atomic_write_pending_text(self, content: str) -> None:
        self.suggestions_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.suggestions_path.parent / f".{self.suggestions_path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8") as fh:
                fh.write(content)
                self._flush_and_fsync(fh)
            os.replace(temp_path, self.suggestions_path)
            try:
                dir_fd = os.open(str(self.suggestions_path.parent), os.O_RDONLY)
            except Exception:
                dir_fd = -1
            if dir_fd >= 0:
                try:
                    os.fsync(dir_fd)
                except Exception:
                    pass
                finally:
                    try:
                        os.close(dir_fd)
                    except Exception:
                        pass
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    @staticmethod
    def _coerce_priority(value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        normalized = str(value or "").strip().lower()
        legacy = {
            "high": 0.9,
            "medium": 0.6,
            "low": 0.3,
        }
        if normalized in legacy:
            return legacy[normalized]
        try:
            parsed = float(normalized)
        except Exception:
            parsed = 0.5
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _delivery_route_from_source(source: str) -> tuple[str, str]:
        raw = str(source or "").strip()
        parts = raw.split(":")
        if len(parts) >= 3 and parts[0].lower() == "session":
            channel = str(parts[1] or "").strip() or "cli"
            target = str(":".join(parts[2:]) or "").strip() or "default"
            return channel, target
        return "cli", "default"

    @staticmethod
    def _parse_time(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    def _read_pending_payload(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.suggestions_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
        except Exception:
            return []
        return []

    def _write_pending_payload(self, rows: list[dict[str, Any]]) -> None:
        self._atomic_write_pending_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")

    def pending(self) -> list[MemorySuggestion]:
        return self._deliverable_suggestions(include_retryable_failed=False)

    @staticmethod
    def _row_status(row: dict[str, Any]) -> str:
        return str(row.get("status", "pending") or "pending").strip().lower() or "pending"

    @staticmethod
    def _row_failure_count(row: dict[str, Any]) -> int:
        try:
            return max(0, int(row.get("failure_count", 0) or 0))
        except Exception:
            return 0

    def _retry_delay_seconds(self, failure_count: int) -> float:
        base = max(0.0, float(self.retry_backoff_seconds or 0.0))
        if base <= 0:
            return 0.0
        attempts = max(1, int(failure_count or 1))
        cap = max(base, base * 8.0)
        return min(base * (2 ** max(0, attempts - 1)), cap)

    def _suggestion_from_row(self, row: dict[str, Any]) -> MemorySuggestion | None:
        text = str(row.get("text", "")).strip()
        if not text:
            return None
        metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
        payload = dict(metadata)
        status = self._row_status(row)
        payload.setdefault("_delivery_status", status)
        failure_count = self._row_failure_count(row)
        if failure_count > 0:
            payload.setdefault("_failure_count", failure_count)
        last_error = str(row.get("last_error", "") or "")
        if last_error:
            payload.setdefault("_last_error", last_error)
        retry_after_at = str(row.get("retry_after_at", "") or "")
        if retry_after_at:
            payload.setdefault("_retry_after_at", retry_after_at)
        return MemorySuggestion(
            text=text,
            priority=self._coerce_priority(row.get("priority", 0.5)),
            trigger=str(row.get("trigger", "unknown") or "unknown"),
            channel=str(row.get("channel", "cli") or "cli"),
            target=str(row.get("target", "default") or "default"),
            metadata=payload,
            created_at=str(row.get("created_at", "") or ""),
        )

    def _row_is_deliverable(self, row: dict[str, Any], *, now: datetime, include_retryable_failed: bool) -> bool:
        status = self._row_status(row)
        if status == "pending":
            return True
        if status != "failed" or not include_retryable_failed:
            return False
        failure_count = max(1, self._row_failure_count(row))
        if failure_count >= self.max_retry_attempts:
            return False
        retry_after_raw = str(row.get("retry_after_at", row.get("failed_at", "")) or "")
        if not retry_after_raw:
            return True
        retry_after_at = self._parse_time(retry_after_raw)
        if retry_after_at.year <= 1:
            return True
        return retry_after_at <= now

    def _deliverable_suggestions(self, *, include_retryable_failed: bool) -> list[MemorySuggestion]:
        suggestions: list[MemorySuggestion] = []
        seen_semantic_keys: set[str] = set()
        now = datetime.now(timezone.utc)
        for row in self._read_pending_payload():
            if not self._row_is_deliverable(row, now=now, include_retryable_failed=include_retryable_failed):
                continue
            suggestion = self._suggestion_from_row(row)
            if suggestion is None:
                continue
            if suggestion.semantic_key in seen_semantic_keys:
                continue
            seen_semantic_keys.add(suggestion.semantic_key)
            suggestions.append(suggestion)
        suggestions.sort(key=lambda item: (str(getattr(item, "created_at", "") or ""), str(item.suggestion_id)))
        return suggestions

    def deliverable(self) -> list[MemorySuggestion]:
        return self._deliverable_suggestions(include_retryable_failed=True)

    def mark_delivered(self, suggestion_id: str | MemorySuggestion) -> bool:
        if isinstance(suggestion_id, MemorySuggestion):
            sid = suggestion_id.suggestion_id
            semantic_key = suggestion_id.semantic_key
        else:
            sid = str(suggestion_id or "")
            semantic_key = ""
        changed = False
        with self._pending_lock:
            rows = self._read_pending_payload()
            for row in rows:
                current_id = str(row.get("id", "") or "")
                current_key = str(row.get("semantic_key", "") or "")
                if current_id != sid and (not semantic_key or current_key != semantic_key):
                    continue
                if row.get("status", "pending") != "delivered":
                    row["status"] = "delivered"
                    row["delivered_at"] = datetime.now(timezone.utc).isoformat()
                    row["last_attempt_at"] = row["delivered_at"]
                    row["retry_after_at"] = ""
                    changed = True
            if changed:
                self._write_pending_payload(rows)
                self._telemetry["sent"] += 1
        return changed

    def mark_failed(self, suggestion_id: str | MemorySuggestion, *, error: str = "") -> bool:
        if isinstance(suggestion_id, MemorySuggestion):
            sid = suggestion_id.suggestion_id
            semantic_key = suggestion_id.semantic_key
        else:
            sid = str(suggestion_id or "")
            semantic_key = ""
        changed = False
        with self._pending_lock:
            rows = self._read_pending_payload()
            now_iso = datetime.now(timezone.utc).isoformat()
            for row in rows:
                current_id = str(row.get("id", "") or "")
                current_key = str(row.get("semantic_key", "") or "")
                if current_id != sid and (not semantic_key or current_key != semantic_key):
                    continue
                failure_count = self._row_failure_count(row) + 1
                retry_delay = self._retry_delay_seconds(failure_count)
                row["status"] = "failed"
                row["failed_at"] = now_iso
                row["last_attempt_at"] = now_iso
                row["failure_count"] = failure_count
                row["retry_after_at"] = (datetime.now(timezone.utc) + timedelta(seconds=retry_delay)).isoformat()
                if error:
                    row["last_error"] = str(error)
                changed = True
            if changed:
                self._write_pending_payload(rows)
                self._telemetry["failed"] += 1
        return changed

    def _latest_delivery_timestamp(self, semantic_key: str) -> datetime | None:
        latest: datetime | None = None
        for row in self._read_pending_payload():
            row_key = str(row.get("semantic_key", "") or "")
            if row_key != semantic_key:
                continue
            for stamp_key in ("delivered_at", "failed_at"):
                stamp = str(row.get(stamp_key, "") or "")
                if not stamp:
                    continue
                parsed = self._parse_time(stamp)
                if parsed.year <= 1:
                    continue
                if latest is None or parsed > latest:
                    latest = parsed
        return latest

    def should_deliver(self, suggestion: MemorySuggestion, *, min_priority: float = 0.0) -> bool:
        priority = self._coerce_priority(getattr(suggestion, "priority", 0.0))
        if priority < float(min_priority):
            self._telemetry["low_priority_skipped"] += 1
            return False
        if self.cooldown_seconds <= 0:
            return True
        latest = self._latest_delivery_timestamp(suggestion.semantic_key)
        if latest is None:
            return True
        now = datetime.now(timezone.utc)
        if (now - latest).total_seconds() < self.cooldown_seconds:
            self._telemetry["cooldown_skipped"] += 1
            return False
        return True

    def telemetry(self) -> dict[str, Any]:
        return {
            **dict(self._telemetry),
            "cooldown_seconds": self.cooldown_seconds,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "max_retry_attempts": self.max_retry_attempts,
            "pending": len(self.pending()),
            "deliverable": len(self.deliverable()),
            "suggestions_path": str(self.suggestions_path),
        }

    def _all_records(self) -> list[MemoryRecord]:
        try:
            return self.store.all() + self.store.curated()
        except Exception:
            return []

    @classmethod
    def _extract_event_date(cls, text: str, now: datetime) -> datetime | None:
        if not text:
            return None
        match = cls._DATE_RE.search(text)
        if match:
            try:
                parsed = datetime.fromisoformat(match.group(1) + "T00:00:00+00:00")
                return parsed.astimezone(timezone.utc)
            except Exception:
                return None

        month_day = cls._MONTH_DAY_RE.search(text)
        if month_day:
            try:
                month = int(month_day.group(1))
                day = int(month_day.group(2))
                candidate = datetime(now.year, month, day, tzinfo=timezone.utc)
                if candidate < now:
                    candidate = datetime(now.year + 1, month, day, tzinfo=timezone.utc)
                return candidate
            except Exception:
                return None
        return None

    @staticmethod
    def _extract_tokens(text: str) -> list[str]:
        return [token.lower() for token in re.findall(r"[a-zA-Z0-9_]+", str(text or "")) if len(token) >= 4]

    def _trigger_upcoming_events(self, records: list[MemoryRecord], now: datetime) -> list[MemorySuggestion]:
        out: list[MemorySuggestion] = []
        horizon = now + timedelta(days=7)
        for row in records:
            text = str(getattr(row, "text", "") or "")
            lowered = text.lower()
            if not (self._BIRTHDAY_RE.search(lowered) or self._TRAVEL_RE.search(lowered)):
                continue
            event_date = self._extract_event_date(text, now)
            if event_date is None or not (now <= event_date <= horizon):
                continue
            trigger = "upcoming_birthday" if self._BIRTHDAY_RE.search(lowered) else "upcoming_travel"
            channel, target = self._delivery_route_from_source(str(getattr(row, "source", "") or ""))
            days_until = max(0, (event_date.date() - now.date()).days)
            event_kind = "birthday" if self._BIRTHDAY_RE.search(lowered) else "travel"
            out.append(
                MemorySuggestion(
                    text=f"Upcoming {event_kind} in {days_until} day(s): {text}",
                    priority=0.9,
                    trigger="upcoming_event",
                    channel=channel,
                    target=target,
                    metadata={
                        "event_date": event_date.date().isoformat(),
                        "days_until": days_until,
                        "record_id": str(getattr(row, "id", "") or ""),
                        "event_kind": event_kind,
                        "legacy_trigger": trigger,
                    },
                    created_at=now.isoformat(),
                )
            )
        return out

    def _trigger_pending_tasks(self, records: list[MemoryRecord], now: datetime) -> list[MemorySuggestion]:
        out: list[MemorySuggestion] = []
        cutoff = now - timedelta(days=2)
        for row in records:
            text = str(getattr(row, "text", "") or "")
            if not self._TASK_RE.search(text) or self._DONE_RE.search(text):
                continue
            created_at = self._parse_time(str(getattr(row, "created_at", "") or ""))
            updated_at = self._parse_time(str(getattr(row, "updated_at", "") or ""))
            latest = max(created_at, updated_at)
            if latest > cutoff:
                continue
            stale_days = max(0, int((now - latest).total_seconds() // 86400))
            channel, target = self._delivery_route_from_source(str(getattr(row, "source", "") or ""))
            out.append(
                MemorySuggestion(
                    text=f"Pending task with no updates for {stale_days} day(s): {text}",
                    priority=0.75,
                    trigger="pending_task",
                    channel=channel,
                    target=target,
                    metadata={
                        "record_id": str(getattr(row, "id", "") or ""),
                        "stale_days": stale_days,
                    },
                    created_at=now.isoformat(),
                )
            )
        return out

    def _trigger_repeated_topics(self, records: list[MemoryRecord], now: datetime) -> list[MemorySuggestion]:
        out: list[MemorySuggestion] = []
        cutoff = now - timedelta(days=7)
        counts: dict[str, int] = {}
        for row in records:
            created_at = self._parse_time(str(getattr(row, "created_at", "") or ""))
            if created_at < cutoff:
                continue
            for token in self._extract_tokens(str(getattr(row, "text", "") or "")):
                counts[token] = counts.get(token, 0) + 1
        for token, count in sorted(counts.items()):
            if count <= 3:
                continue
            out.append(
                MemorySuggestion(
                    text=f"Pattern detected: '{token}' appeared {count} times in the last 7 days.",
                    priority=0.72,
                    trigger="pattern",
                    channel="cli",
                    target="profile",
                    metadata={"topic": token, "count": count},
                    created_at=now.isoformat(),
                )
            )
        return out

    def _trigger_recurring_birthdays(self, records: list[MemoryRecord], now: datetime) -> list[MemorySuggestion]:
        out: list[MemorySuggestion] = []
        by_month_day: dict[str, int] = {}
        for row in records:
            text = str(getattr(row, "text", "") or "")
            if not self._BIRTHDAY_RE.search(text):
                continue
            event_date = self._extract_event_date(text, now)
            if event_date is None:
                continue
            key = event_date.strftime("%m-%d")
            by_month_day[key] = by_month_day.get(key, 0) + 1
        for month_day, count in sorted(by_month_day.items()):
            if count < 2:
                continue
            out.append(
                MemorySuggestion(
                    text=f"Pattern detected: recurring birthday date {month_day} appears in {count} records.",
                    priority=0.65,
                    trigger="pattern",
                    channel="cli",
                    target="profile",
                    metadata={"month_day": month_day, "count": count},
                    created_at=now.isoformat(),
                )
            )
        return out

    def _persist_pending(self, suggestions: list[MemorySuggestion]) -> None:
        with self._pending_lock:
            rows = self._read_pending_payload()
            by_id = {str(item.get("id", "")): item for item in rows if isinstance(item, dict)}
            by_semantic = {
                str(item.get("semantic_key", "")): item
                for item in rows
                if isinstance(item, dict) and str(item.get("semantic_key", "")).strip()
            }
            for suggestion in suggestions:
                suggestion_payload = suggestion.to_payload()
                suggestion_payload["status"] = "pending"
                sid = suggestion_payload.get("id", "")
                semantic_key = str(suggestion_payload.get("semantic_key", "") or "")
                existing = by_semantic.get(semantic_key)
                if existing is not None:
                    if self._row_status(existing) != "delivered":
                        existing["text"] = suggestion_payload.get("text", existing.get("text", ""))
                        existing["priority"] = suggestion_payload.get("priority", existing.get("priority", 0.5))
                        existing["trigger"] = suggestion_payload.get("trigger", existing.get("trigger", "unknown"))
                        existing["channel"] = suggestion_payload.get("channel", existing.get("channel", "cli"))
                        existing["target"] = suggestion_payload.get("target", existing.get("target", "default"))
                        existing["metadata"] = suggestion_payload.get("metadata", existing.get("metadata", {}))
                        existing["semantic_key"] = semantic_key
                        if not str(existing.get("created_at", "") or "").strip():
                            existing["created_at"] = suggestion_payload.get("created_at", "")
                    self._telemetry["deduped"] += 1
                    continue
                if sid in by_id and by_id[sid].get("status") == "delivered":
                    self._telemetry["deduped"] += 1
                    continue
                by_id[str(sid)] = suggestion_payload
                if semantic_key:
                    by_semantic[semantic_key] = suggestion_payload
            merged = list(by_id.values())
            merged.sort(key=lambda row: str(row.get("created_at", "")))
            self._write_pending_payload(merged)

    def _scan_suggestions(self, *, now: datetime, records: list[MemoryRecord]) -> list[MemorySuggestion]:
        suggestions: list[MemorySuggestion] = []
        suggestions.extend(self._trigger_upcoming_events(records, now))
        suggestions.extend(self._trigger_pending_tasks(records, now))
        suggestions.extend(self._trigger_repeated_topics(records, now))
        suggestions.extend(self._trigger_recurring_birthdays(records, now))
        self._telemetry["generated"] += len(suggestions)
        return suggestions

    def _purge_expired_records(self) -> None:
        try:
            purge_fn = getattr(self.store, "purge_expired_records", None)
            if callable(purge_fn):
                purge_fn()
        except Exception:
            pass

    async def scan(self) -> list[MemorySuggestion]:
        self._telemetry["scans"] += 1
        now = datetime.now(timezone.utc)
        records = await asyncio.to_thread(self._all_records)
        suggestions = self._scan_suggestions(now=now, records=records)
        await asyncio.to_thread(self._persist_pending, suggestions)
        await asyncio.to_thread(self._purge_expired_records)
        return await asyncio.to_thread(self.deliverable)

    def scan_sync(self) -> list[MemorySuggestion]:
        self._telemetry["scans"] += 1
        now = datetime.now(timezone.utc)
        records = self._all_records()
        suggestions = self._scan_suggestions(now=now, records=records)
        self._persist_pending(suggestions)
        self._purge_expired_records()
        return self.deliverable()
