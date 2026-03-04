from __future__ import annotations

import asyncio
import json
import hashlib
import re
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
        if not payload.get("created_at"):
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        return payload

    @property
    def suggestion_id(self) -> str:
        base = f"{self.trigger}|{self.target}|{self.text}".strip().lower()
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


class MemoryMonitor:
    _DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
    _MONTH_DAY_RE = re.compile(r"\b(\d{2})[-/](\d{2})\b")
    _TASK_RE = re.compile(r"\b(todo|pendente|pending|task|tarefa|fazer)\b", re.IGNORECASE)
    _DONE_RE = re.compile(r"\b(done|feito|concluido|concluído|resolved|resolvido)\b", re.IGNORECASE)
    _BIRTHDAY_RE = re.compile(r"\b(birthday|aniversario|aniversário)\b", re.IGNORECASE)
    _TRAVEL_RE = re.compile(r"\b(travel|trip|viagem|voo|flight)\b", re.IGNORECASE)

    def __init__(self, store: MemoryStore | None = None, *, suggestions_path: str | Path | None = None) -> None:
        self.store = store or MemoryStore()
        self.suggestions_path = Path(suggestions_path) if suggestions_path else (self.store.memory_home / "suggestions_pending.json")
        self.suggestions_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.suggestions_path.exists():
            self.suggestions_path.write_text("[]\n", encoding="utf-8")

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
        self.suggestions_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def pending(self) -> list[MemorySuggestion]:
        suggestions: list[MemorySuggestion] = []
        for row in self._read_pending_payload():
            if row.get("status", "pending") != "pending":
                continue
            text = str(row.get("text", "")).strip()
            if not text:
                continue
            suggestions.append(
                MemorySuggestion(
                    text=text,
                    priority=self._coerce_priority(row.get("priority", 0.5)),
                    trigger=str(row.get("trigger", "unknown") or "unknown"),
                    channel=str(row.get("channel", "cli") or "cli"),
                    target=str(row.get("target", "default") or "default"),
                    metadata=row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {},
                    created_at=str(row.get("created_at", "") or ""),
                )
            )
        return suggestions

    def mark_delivered(self, suggestion_id: str) -> bool:
        changed = False
        rows = self._read_pending_payload()
        for row in rows:
            current_id = str(row.get("id", "") or "")
            if current_id != str(suggestion_id or ""):
                continue
            if row.get("status", "pending") != "delivered":
                row["status"] = "delivered"
                row["delivered_at"] = datetime.now(timezone.utc).isoformat()
                changed = True
        if changed:
            self._write_pending_payload(rows)
        return changed

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
        rows = self._read_pending_payload()
        by_id = {str(item.get("id", "")): item for item in rows if isinstance(item, dict)}
        for suggestion in suggestions:
            suggestion_payload = suggestion.to_payload()
            suggestion_payload["status"] = "pending"
            sid = suggestion_payload.get("id", "")
            if sid in by_id and by_id[sid].get("status") == "delivered":
                continue
            by_id[str(sid)] = suggestion_payload
        merged = list(by_id.values())
        merged.sort(key=lambda row: str(row.get("created_at", "")))
        self._write_pending_payload(merged)

    async def scan(self) -> list[MemorySuggestion]:
        now = datetime.now(timezone.utc)
        records = await asyncio.to_thread(self._all_records)
        suggestions: list[MemorySuggestion] = []
        suggestions.extend(self._trigger_upcoming_events(records, now))
        suggestions.extend(self._trigger_pending_tasks(records, now))
        suggestions.extend(self._trigger_repeated_topics(records, now))
        suggestions.extend(self._trigger_recurring_birthdays(records, now))
        self._persist_pending(suggestions)
        return self.pending()
