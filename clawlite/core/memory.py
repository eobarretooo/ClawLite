from __future__ import annotations

import json
import hashlib
import re
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover
    BM25Okapi = None

WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
TRIVIAL_RE = re.compile(
    r"^(ok|okay|kk|thanks|thank you|got it|noted|done|cool|yes|no|right|understood|perfeito|blz)[.!?]*$",
    re.IGNORECASE,
)
CURATION_HINT_RE = re.compile(
    r"\b(remember|memory|prefer|preference|timezone|time zone|name|project|deadline|important|always|never|avoid|do not|don't|cannot|can't|must|language|stack)\b",
    re.IGNORECASE,
)

try:
    import fcntl
except Exception:  # pragma: no cover - platform fallback
    fcntl = None


@dataclass(slots=True)
class MemoryRecord:
    id: str
    text: str
    source: str
    created_at: str


class MemoryStore:
    """Durable two-layer memory with optional history/curated split."""

    _MAX_HISTORY_RECORDS = 2000
    _MAX_CURATED_FACTS = 250
    _MAX_CURATED_SESSIONS_PER_FACT = 12
    _MAX_CHECKPOINT_SOURCES = 4096
    _MAX_CHECKPOINT_SIGNATURES = 4096

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        history_path: str | Path | None = None,
        curated_path: str | Path | None = None,
        checkpoints_path: str | Path | None = None,
        split_layers: bool = True,
    ) -> None:
        base_history = Path(history_path) if history_path else (Path(db_path) if db_path else (Path.home() / ".clawlite" / "state" / "memory.jsonl"))
        self.path = base_history  # Backward-compatible alias.
        self.history_path = base_history

        if curated_path:
            self.curated_path = Path(curated_path)
        elif split_layers:
            self.curated_path = self.history_path.with_name("memory_curated.json")
        else:
            self.curated_path = None

        if checkpoints_path:
            self.checkpoints_path = Path(checkpoints_path)
        else:
            self.checkpoints_path = self.history_path.with_name("memory_checkpoints.json")

        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.history_path, default="")
        if self.curated_path is not None:
            self.curated_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_file(self.curated_path, default='{"version": 2, "facts": []}\n')
        self.checkpoints_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.checkpoints_path, default="{}\n")
        self._diagnostics: dict[str, int | str] = {
            "history_read_corrupt_lines": 0,
            "history_repaired_files": 0,
            "consolidate_writes": 0,
            "consolidate_dedup_hits": 0,
            "session_recovery_attempts": 0,
            "session_recovery_hits": 0,
            "last_error": "",
        }

    @staticmethod
    def _ensure_file(path: Path, *, default: str) -> None:
        if path.exists():
            return
        path.write_text(default, encoding="utf-8")

    @contextmanager
    def _locked_file(self, path: Path, mode: str, *, exclusive: bool):
        with path.open(mode, encoding="utf-8") as fh:
            if fcntl is not None:
                lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(fh.fileno(), lock_mode)
            try:
                yield fh
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _normalize_memory_text(text: str) -> str:
        return " ".join(WORD_RE.findall(text.lower()))

    @staticmethod
    def _is_trivial_message(text: str) -> bool:
        compact = " ".join(str(text or "").split())
        if not compact:
            return True
        if len(compact) <= 4:
            return True
        return bool(TRIVIAL_RE.match(compact))

    @staticmethod
    def _is_curation_candidate(role: str, content: str) -> bool:
        clean_role = str(role or "").strip().lower()
        clean_content = " ".join(str(content or "").split())
        if not clean_content or MemoryStore._is_trivial_message(clean_content):
            return False
        if CURATION_HINT_RE.search(clean_content):
            return True
        if clean_role == "user" and len(clean_content) >= 96:
            return True
        return False

    @staticmethod
    def _chunk_signature(lines: list[str]) -> str:
        raw = "\n".join(lines).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _parse_checkpoints(raw: str) -> dict[str, dict[str, object]]:
        empty_state = {
            "source_signatures": {},
            "source_activity": {},
            "global_signatures": {},
        }
        payload_raw = raw.strip()
        if not payload_raw:
            return empty_state
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            return empty_state
        if not isinstance(payload, dict):
            return empty_state

        has_v2_shape = any(key in payload for key in ("source_signatures", "global_signatures", "source_activity"))
        if not has_v2_shape:
            legacy_signatures = {
                str(k): str(v)
                for k, v in payload.items()
                if isinstance(k, str) and isinstance(v, str)
            }
            return {
                "source_signatures": legacy_signatures,
                "source_activity": {},
                "global_signatures": {},
            }

        source_signatures_raw = payload.get("source_signatures", {})
        source_activity_raw = payload.get("source_activity", {})
        global_signatures_raw = payload.get("global_signatures", {})

        source_signatures = {}
        if isinstance(source_signatures_raw, dict):
            source_signatures = {
                str(k): str(v)
                for k, v in source_signatures_raw.items()
                if isinstance(k, str) and isinstance(v, str)
            }

        source_activity = {}
        if isinstance(source_activity_raw, dict):
            source_activity = {
                str(k): str(v)
                for k, v in source_activity_raw.items()
                if isinstance(k, str) and isinstance(v, str)
            }

        global_signatures: dict[str, dict[str, object]] = {}
        if isinstance(global_signatures_raw, dict):
            for key, value in global_signatures_raw.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                count_raw = value.get("count", 0)
                try:
                    count = int(count_raw)
                except Exception:
                    count = 0
                global_signatures[str(key)] = {
                    "count": max(0, count),
                    "last_seen_at": str(value.get("last_seen_at", "") or ""),
                    "last_source": str(value.get("last_source", "") or ""),
                }

        return {
            "source_signatures": source_signatures,
            "source_activity": source_activity,
            "global_signatures": global_signatures,
        }

    @staticmethod
    def _format_checkpoints(payload: dict[str, dict[str, object]]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"

    @staticmethod
    def _parse_iso_timestamp(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    @classmethod
    def _normalize_curated_fact(cls, row: dict[str, object]) -> dict[str, object] | None:
        text = str(row.get("text", "")).strip()
        if not text:
            return None
        created_at = str(row.get("created_at", "") or datetime.now(timezone.utc).isoformat())
        last_seen_at = str(row.get("last_seen_at", "") or created_at)
        try:
            mentions = int(row.get("mentions", 1))
        except Exception:
            mentions = 1
        try:
            session_count = int(row.get("session_count", 1))
        except Exception:
            session_count = 1
        try:
            importance = float(row.get("importance", 1.0))
        except Exception:
            importance = 1.0

        sessions_raw = row.get("sessions", [])
        sessions: list[str] = []
        if isinstance(sessions_raw, list):
            for session in sessions_raw:
                clean = str(session or "").strip()
                if clean and clean not in sessions:
                    sessions.append(clean)

        return {
            "id": str(row.get("id", "") or uuid.uuid4().hex),
            "text": text,
            "source": str(row.get("source", "curated") or "curated"),
            "created_at": created_at,
            "last_seen_at": last_seen_at,
            "mentions": max(1, mentions),
            "session_count": max(1, session_count),
            "sessions": sessions[-cls._MAX_CURATED_SESSIONS_PER_FACT :],
            "importance": max(0.1, importance),
        }

    def _curated_rank(self, row: dict[str, object]) -> tuple[float, int, int, datetime, datetime, str, str]:
        importance = float(row.get("importance", 0.0))
        mentions = int(row.get("mentions", 0))
        session_count = int(row.get("session_count", 0))
        last_seen = self._parse_iso_timestamp(str(row.get("last_seen_at", "")))
        created = self._parse_iso_timestamp(str(row.get("created_at", "")))
        text = str(row.get("text", ""))
        rid = str(row.get("id", ""))
        return (importance, mentions, session_count, last_seen, created, text, rid)

    def _prune_history(self) -> None:
        with self._locked_file(self.history_path, "r+", exclusive=True) as fh:
            lines = fh.read().splitlines()
            if len(lines) <= self._MAX_HISTORY_RECORDS:
                return
            kept = lines[-self._MAX_HISTORY_RECORDS :]
            fh.seek(0)
            fh.truncate()
            fh.write("\n".join(kept) + "\n")
            fh.flush()

    def _read_curated_facts(self) -> list[dict[str, object]]:
        if self.curated_path is None:
            return []
        with self._locked_file(self.curated_path, "r", exclusive=False) as fh:
            raw = fh.read().strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        facts = payload.get("facts", [])
        if not isinstance(facts, list):
            return []
        out: list[dict[str, object]] = []
        for row in facts:
            if not isinstance(row, dict):
                continue
            normalized = self._normalize_curated_fact(row)
            if normalized is None:
                continue
            out.append(normalized)
        return out

    def _write_curated_facts(self, facts: list[dict[str, object]]) -> None:
        if self.curated_path is None:
            return
        normalized: list[dict[str, object]] = []
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            clean = self._normalize_curated_fact(fact)
            if clean is not None:
                normalized.append(clean)

        normalized.sort(key=self._curated_rank, reverse=True)
        payload = {"version": 2, "facts": normalized[: self._MAX_CURATED_FACTS]}
        encoded = json.dumps(payload, ensure_ascii=False, indent=2)
        with self._locked_file(self.curated_path, "w", exclusive=True) as fh:
            fh.write(encoded)
            fh.write("\n")
            fh.flush()

    @staticmethod
    def _source_session_key(source: str) -> str:
        return str(source or "").strip().lower() or "unknown"

    @staticmethod
    def _candidate_importance(*, role: str, text: str, repeated_count: int) -> float:
        score = 1.0
        if role == "user":
            score += 0.5
        if CURATION_HINT_RE.search(text):
            score += 1.0
        score += min(0.8, len(text) / 320.0)
        score += min(2.0, max(0, repeated_count - 1) * 0.35)
        return score

    def _curate_candidates(self, candidates: list[tuple[str, str]], *, source: str, repeated_count: int = 1) -> None:
        if self.curated_path is None or not candidates:
            return
        current = self._read_curated_facts()
        by_norm = {self._normalize_memory_text(str(item["text"])): item for item in current}
        now_iso = datetime.now(timezone.utc).isoformat()
        source_session = self._source_session_key(source)
        changed = False
        for role, candidate in candidates:
            norm = self._normalize_memory_text(candidate)
            if not norm:
                continue
            existing = by_norm.get(norm)
            if existing is None:
                row: dict[str, object] = {
                    "id": uuid.uuid4().hex,
                    "text": candidate,
                    "source": f"curated:{source}",
                    "created_at": now_iso,
                    "last_seen_at": now_iso,
                    "mentions": 1,
                    "session_count": 1,
                    "sessions": [source_session],
                    "importance": self._candidate_importance(role=role, text=candidate, repeated_count=repeated_count),
                }
                current.append(row)
                by_norm[norm] = row
                changed = True
                continue

            existing_sessions = existing.get("sessions", [])
            if not isinstance(existing_sessions, list):
                existing_sessions = []
            clean_sessions = []
            for raw_session in existing_sessions:
                clean = str(raw_session or "").strip().lower()
                if clean and clean not in clean_sessions:
                    clean_sessions.append(clean)
            if source_session not in clean_sessions:
                clean_sessions.append(source_session)

            old_mentions = int(existing.get("mentions", 1))
            old_session_count = int(existing.get("session_count", max(1, len(clean_sessions))))
            old_importance = float(existing.get("importance", 1.0))
            existing["mentions"] = old_mentions + 1
            existing["session_count"] = max(old_session_count, len(clean_sessions))
            existing["last_seen_at"] = now_iso
            existing["sessions"] = clean_sessions[-self._MAX_CURATED_SESSIONS_PER_FACT :]
            existing["importance"] = old_importance + self._candidate_importance(
                role=role,
                text=candidate,
                repeated_count=repeated_count,
            ) * 0.35
            changed = True
        if changed:
            self._write_curated_facts(current)

    def _extract_consolidation_lines(self, messages: Iterable[dict[str, str]]) -> list[str]:
        lines: list[str] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            content = " ".join(str(msg.get("content", "")).split())
            if role not in {"user", "assistant"}:
                continue
            if not self._is_curation_candidate(role, content):
                continue
            lines.append(f"{role}: {content}")
        return lines

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
        with self._locked_file(self.history_path, "a", exclusive=True) as fh:
            fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
            fh.flush()
        self._prune_history()
        return row

    def _read_history_records(self) -> list[MemoryRecord]:
        out: list[MemoryRecord] = []
        valid_lines: list[str] = []
        corrupt_lines = 0
        with self._locked_file(self.history_path, "r", exclusive=False) as fh:
            lines = fh.read().splitlines()
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                corrupt_lines += 1
                continue
            if not isinstance(payload, dict):
                corrupt_lines += 1
                continue
            valid_lines.append(raw)
            text = str(payload.get("text", "")).strip()
            if not text:
                continue
            out.append(
                MemoryRecord(
                    id=str(payload.get("id", "")),
                    text=text,
                    source=str(payload.get("source", "unknown")),
                    created_at=str(payload.get("created_at", "")),
                )
            )

        if corrupt_lines:
            self._diagnostics["history_read_corrupt_lines"] = int(self._diagnostics["history_read_corrupt_lines"]) + corrupt_lines
            self._repair_history_file(valid_lines)

        return out

    def _repair_history_file(self, valid_lines: list[str]) -> None:
        try:
            rewritten = "\n".join(valid_lines)
            if rewritten:
                rewritten = f"{rewritten}\n"
            with self._locked_file(self.history_path, "w", exclusive=True) as fh:
                fh.write(rewritten)
                fh.flush()
            self._diagnostics["history_repaired_files"] = int(self._diagnostics["history_repaired_files"]) + 1
            self._diagnostics["last_error"] = ""
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

    def all(self) -> list[MemoryRecord]:
        return self._read_history_records()

    def curated(self) -> list[MemoryRecord]:
        rows = self._read_curated_facts()
        return [
            MemoryRecord(
                id=str(item.get("id", "")),
                text=str(item.get("text", "")).strip(),
                source=str(item.get("source", "curated")),
                created_at=str(item.get("created_at", "")),
            )
            for item in rows
            if str(item.get("text", "")).strip()
        ]

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        curated_rows = self._read_curated_facts()
        curated_records = [
            MemoryRecord(
                id=str(item.get("id", "")),
                text=str(item.get("text", "")).strip(),
                source=str(item.get("source", "curated")),
                created_at=str(item.get("created_at", "")),
            )
            for item in curated_rows
            if str(item.get("text", "")).strip()
        ]
        curated_importance = {str(item.get("id", "")): float(item.get("importance", 1.0)) for item in curated_rows}
        curated_mentions = {str(item.get("id", "")): int(item.get("mentions", 1)) for item in curated_rows}

        records = curated_records + self.all()
        if not records:
            return []

        q_tokens = self._tokens(query)
        if not q_tokens:
            return records[-limit:][::-1]

        corpus_tokens = [self._tokens(item.text) for item in records]
        qset = set(q_tokens)

        bm25_scores: list[float]
        if BM25Okapi is None:
            bm25_scores = [0.0 for _ in records]
        else:
            bm25 = BM25Okapi(corpus_tokens)
            scores = bm25.get_scores(q_tokens)
            bm25_scores = [float(scores[idx]) for idx in range(len(records))]

        # Primary key: lexical overlap with query terms.
        # Secondary key: BM25 score for ordering among matching records.
        scored: list[tuple[float, float, int]] = []
        for idx, toks in enumerate(corpus_tokens):
            overlap = len(qset.intersection(toks))
            curated_boost = 0.0
            if records[idx].source.startswith("curated:"):
                importance = curated_importance.get(records[idx].id, 1.0)
                mentions = curated_mentions.get(records[idx].id, 1)
                curated_boost = 0.75 + min(2.0, importance * 0.25) + min(1.0, mentions * 0.1)
            scored.append((float(overlap) + curated_boost, bm25_scores[idx], idx))

        scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

        picked: list[MemoryRecord] = []
        for overlap_score, bm25_score, idx in scored:
            if len(picked) >= limit:
                break
            if overlap_score <= 0 and bm25_score <= 0.0:
                continue
            picked.append(records[idx])

        return picked if picked else records[-limit:][::-1]

    def consolidate(self, messages: Iterable[dict[str, str]], *, source: str = "session") -> MemoryRecord | None:
        lines = self._extract_consolidation_lines(messages)
        if not lines:
            return None

        summary_lines = lines[-6:]
        signature = self._chunk_signature(summary_lines)

        with self._locked_file(self.checkpoints_path, "r+", exclusive=True) as checkpoints_fh:
            checkpoints = self._parse_checkpoints(checkpoints_fh.read())
            source_signatures = checkpoints.get("source_signatures", {})
            if not isinstance(source_signatures, dict):
                source_signatures = {}

            source_activity = checkpoints.get("source_activity", {})
            if not isinstance(source_activity, dict):
                source_activity = {}

            global_signatures = checkpoints.get("global_signatures", {})
            if not isinstance(global_signatures, dict):
                global_signatures = {}

            if source_signatures.get(source) == signature:
                self._diagnostics["consolidate_dedup_hits"] = int(self._diagnostics["consolidate_dedup_hits"]) + 1
                return None

            summary = "\n".join(summary_lines)
            row = self.add(summary, source=source)
            self._diagnostics["consolidate_writes"] = int(self._diagnostics["consolidate_writes"]) + 1

            now_iso = datetime.now(timezone.utc).isoformat()
            source_signatures[source] = signature
            source_activity[source] = now_iso

            global_signature_row = global_signatures.get(signature)
            current_count = 0
            if isinstance(global_signature_row, dict):
                try:
                    current_count = int(global_signature_row.get("count", 0))
                except Exception:
                    current_count = 0
            repeated_count = max(1, current_count + 1)
            global_signatures[signature] = {
                "count": repeated_count,
                "last_seen_at": now_iso,
                "last_source": source,
            }

            if len(source_signatures) > self._MAX_CHECKPOINT_SOURCES:
                ordered_sources = sorted(
                    source_signatures.keys(),
                    key=lambda key: source_activity.get(key, ""),
                )
                drop = len(source_signatures) - self._MAX_CHECKPOINT_SOURCES
                for key in ordered_sources[:drop]:
                    source_signatures.pop(key, None)
                    source_activity.pop(key, None)

            if len(global_signatures) > self._MAX_CHECKPOINT_SIGNATURES:
                ordered_signatures = sorted(
                    global_signatures.keys(),
                    key=lambda key: str(global_signatures.get(key, {}).get("last_seen_at", "")),
                )
                drop = len(global_signatures) - self._MAX_CHECKPOINT_SIGNATURES
                for key in ordered_signatures[:drop]:
                    global_signatures.pop(key, None)

            checkpoints = {
                "source_signatures": source_signatures,
                "source_activity": source_activity,
                "global_signatures": global_signatures,
            }
            checkpoints_fh.seek(0)
            checkpoints_fh.truncate()
            checkpoints_fh.write(self._format_checkpoints(checkpoints))
            checkpoints_fh.flush()

        curated_candidates: list[tuple[str, str]] = []
        for line in summary_lines:
            if ":" not in line:
                continue
            role, value = line.split(":", 1)
            curated_candidates.append((role.strip().lower(), value.strip()))
        self._curate_candidates(curated_candidates, source=source, repeated_count=repeated_count)
        return row

    def recover_session_context(self, session_id: str, *, limit: int = 4) -> list[str]:
        self._diagnostics["session_recovery_attempts"] = int(self._diagnostics["session_recovery_attempts"]) + 1
        bounded_limit = max(1, int(limit or 1))
        clean_session_id = str(session_id or "").strip()
        normalized_targets = {
            clean_session_id,
            f"session:{clean_session_id}" if clean_session_id else "",
        }
        normalized_targets.discard("")
        normalized_session_targets = {
            self._source_session_key(clean_session_id),
            self._source_session_key(f"session:{clean_session_id}"),
        }

        picked: list[str] = []
        seen: set[str] = set()

        history_rows = self._read_history_records()
        for row in reversed(history_rows):
            if row.source not in normalized_targets:
                continue
            snippet = row.text.strip()
            if not snippet or snippet in seen:
                continue
            seen.add(snippet)
            picked.append(snippet)
            if len(picked) >= bounded_limit:
                break

        if len(picked) < bounded_limit:
            for fact in self._read_curated_facts():
                sessions = fact.get("sessions", [])
                if not isinstance(sessions, list):
                    continue
                normalized_sessions = {self._source_session_key(str(item or "")) for item in sessions}
                if not normalized_sessions.intersection(normalized_session_targets):
                    continue
                snippet = str(fact.get("text", "")).strip()
                if not snippet or snippet in seen:
                    continue
                seen.add(snippet)
                picked.append(snippet)
                if len(picked) >= bounded_limit:
                    break

        if picked:
            self._diagnostics["session_recovery_hits"] = int(self._diagnostics["session_recovery_hits"]) + 1

        return picked

    def diagnostics(self) -> dict[str, int | str]:
        return {
            "history_read_corrupt_lines": int(self._diagnostics["history_read_corrupt_lines"]),
            "history_repaired_files": int(self._diagnostics["history_repaired_files"]),
            "consolidate_writes": int(self._diagnostics["consolidate_writes"]),
            "consolidate_dedup_hits": int(self._diagnostics["consolidate_dedup_hits"]),
            "session_recovery_attempts": int(self._diagnostics["session_recovery_attempts"]),
            "session_recovery_hits": int(self._diagnostics["session_recovery_hits"]),
            "last_error": str(self._diagnostics["last_error"]),
        }


# Backward-compatible API expected by legacy CLI.
def add_note(text: str) -> None:
    MemoryStore().add(text, source="legacy")


def search_notes(query: str, limit: int = 10) -> list[str]:
    return [row.text for row in MemoryStore().search(query, limit=limit)]
