from __future__ import annotations

import json
import gzip
import hashlib
import math
import re
import asyncio
import threading
import unicodedata
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

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
EMOTIONAL_MARKERS: dict[str, tuple[str, ...]] = {
    "excited": ("🎉", "incrível", "amei", "!!", "consegui", "funcionou", "perfeito"),
    "frustrated": ("não funciona", "odeio", "absurdo", "de novo isso", "erro", "falhou"),
    "sad": ("triste", "mal", "cansado", "desanimado", "difícil"),
    "positive": ("ótimo", "obrigado", "ajudou", "certo", "legal"),
}
PROFILE_TOPIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "uma",
        "com",
        "para",
        "você",
        "voce",
        "meu",
        "minha",
        "about",
        "from",
        "your",
        "you",
        "sobre",
        "prefiro",
        "respostas",
        "resposta",
    }
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
    category: str = "context"
    user_id: str = "default"
    layer: str = "item"
    modality: str = "text"
    updated_at: str = ""
    confidence: float = 1.0
    decay_rate: float = 0.0
    emotional_tone: str = "neutral"


class MemoryLayer(str, Enum):
    RESOURCE = "resource"
    ITEM = "item"
    CATEGORY = "category"


class MemoryStore:
    """Durable two-layer memory with optional history/curated split."""

    _MAX_HISTORY_RECORDS = 2000
    _MAX_CURATED_FACTS = 250
    _MAX_CURATED_SESSIONS_PER_FACT = 12
    _MAX_CHECKPOINT_SOURCES = 4096
    _MAX_CHECKPOINT_SIGNATURES = 4096
    _RECENCY_MAX_BOOST = 0.35
    _RECENCY_HALF_LIFE_HOURS = 24.0 * 21.0
    _TEMPORAL_INTENT_MATCH_BOOST = 0.2
    _TEMPORAL_INTENT_MISS_PENALTY = 0.05
    _TEMPORAL_RECENCY_RELEVANCE_MIN = 0.1
    _TEMPORAL_QUERY_TOKENS: frozenset[str] = frozenset(
        {
            "today",
            "tomorrow",
            "tonight",
            "yesterday",
            "deadline",
            "deadlines",
            "date",
            "time",
            "when",
            "week",
            "month",
            "quarter",
            "year",
            "next",
            "upcoming",
            "soon",
            "due",
            "calendar",
            "agenda",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
    )
    _TEMPORAL_MEMORY_TOKENS: frozenset[str] = frozenset(
        {
            "today",
            "tomorrow",
            "tonight",
            "yesterday",
            "deadline",
            "due",
            "morning",
            "afternoon",
            "evening",
            "night",
            "week",
            "month",
            "quarter",
            "year",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
            "january",
            "february",
            "march",
            "april",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
            "am",
            "pm",
            "utc",
        }
    )
    _TEMPORAL_VALUE_RE = re.compile(
        r"(?:\b\d{1,2}:\d{2}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}\s*(?:am|pm)\b)",
        re.IGNORECASE,
    )
    _SEMANTIC_BM25_WEIGHT = 0.4
    _SEMANTIC_VECTOR_WEIGHT = 0.6
    _MEMORY_CATEGORIES: tuple[str, ...] = (
        "preferences",
        "facts",
        "decisions",
        "skills",
        "context",
        "relationships",
    )

    @staticmethod
    def _normalize_layer(value: Any) -> str:
        if isinstance(value, MemoryLayer):
            return value.value
        normalized = str(value or "").strip().lower()
        if normalized in {MemoryLayer.RESOURCE.value, MemoryLayer.ITEM.value, MemoryLayer.CATEGORY.value}:
            return normalized
        return MemoryLayer.ITEM.value

    @classmethod
    def _record_from_payload(cls, payload: dict[str, Any]) -> MemoryRecord | None:
        text = str(payload.get("text", "")).strip()
        if not text:
            return None

        try:
            confidence = float(payload.get("confidence", 1.0) or 1.0)
        except Exception:
            confidence = 1.0
        try:
            decay_rate = float(payload.get("decay_rate", payload.get("decayRate", 0.0)) or 0.0)
        except Exception:
            decay_rate = 0.0

        return MemoryRecord(
            id=str(payload.get("id", "")),
            text=text,
            source=str(payload.get("source", "unknown")),
            created_at=str(payload.get("created_at", "")),
            category=str(payload.get("category", "context") or "context"),
            user_id=str(payload.get("user_id", payload.get("userId", "default")) or "default"),
            layer=cls._normalize_layer(payload.get("layer", "item")),
            modality=str(payload.get("modality", "text") or "text"),
            updated_at=str(payload.get("updated_at", payload.get("updatedAt", "")) or ""),
            confidence=confidence,
            decay_rate=decay_rate,
            emotional_tone=str(payload.get("emotional_tone", payload.get("emotionalTone", "neutral")) or "neutral"),
        )

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        history_path: str | Path | None = None,
        curated_path: str | Path | None = None,
        checkpoints_path: str | Path | None = None,
        embeddings_path: str | Path | None = None,
        split_layers: bool = True,
        semantic_enabled: bool = False,
        memory_auto_categorize: bool = False,
        emotional_tracking: bool = False,
        memory_home: str | Path | None = None,
    ) -> None:
        base_history = Path(history_path) if history_path else (Path(db_path) if db_path else (Path.home() / ".clawlite" / "state" / "memory.jsonl"))
        self.path = base_history  # Backward-compatible alias.
        self.history_path = base_history
        if memory_home:
            derived_home = Path(memory_home)
        elif db_path is not None or history_path is not None:
            history_parent = self.history_path.parent
            if history_parent.name == "state":
                derived_home = history_parent.parent / "memory"
            else:
                derived_home = history_parent / "memory"
        else:
            derived_home = Path.home() / ".clawlite" / "memory"
        self.memory_home = derived_home
        self.resources_path = self.memory_home / "resources"
        self.items_path = self.memory_home / "items"
        self.categories_path = self.memory_home / "categories"
        self.embeddings_home = self.memory_home / "embeddings"
        self.emotional_path = self.memory_home / "emotional"
        self.privacy_path = self.memory_home / "privacy.json"
        self.versions_path = self.memory_home / "versions"
        self.users_path = self.memory_home / "users"
        self.shared_path = self.memory_home / "shared"
        self.profile_path = self.emotional_path / "profile.json"
        self._legacy_profile_path = self.memory_home / "profile.json"

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

        self._embeddings_path_explicit = bool(embeddings_path)
        if embeddings_path:
            self.embeddings_path = Path(embeddings_path)
        else:
            self.embeddings_path = self.embeddings_home / "embeddings.jsonl"

        self.semantic_enabled = bool(semantic_enabled)
        self.memory_auto_categorize = bool(memory_auto_categorize)
        self.emotional_tracking = bool(emotional_tracking)

        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_home.mkdir(parents=True, exist_ok=True)
        self.resources_path.mkdir(parents=True, exist_ok=True)
        self.items_path.mkdir(parents=True, exist_ok=True)
        self.categories_path.mkdir(parents=True, exist_ok=True)
        self.embeddings_home.mkdir(parents=True, exist_ok=True)
        self.emotional_path.mkdir(parents=True, exist_ok=True)
        self.versions_path.mkdir(parents=True, exist_ok=True)
        self.users_path.mkdir(parents=True, exist_ok=True)
        self.shared_path.mkdir(parents=True, exist_ok=True)

        if (not self.profile_path.exists()) and self._legacy_profile_path.exists():
            self.profile_path.write_text(self._legacy_profile_path.read_text(encoding="utf-8"), encoding="utf-8")

        if (not self._embeddings_path_explicit) and (not self.embeddings_path.exists()):
            legacy_embeddings_path = self.history_path.parent / "embeddings.jsonl"
            if legacy_embeddings_path != self.embeddings_path and legacy_embeddings_path.exists():
                self.embeddings_path.write_text(legacy_embeddings_path.read_text(encoding="utf-8"), encoding="utf-8")

        self._ensure_file(self.history_path, default="")
        if self.curated_path is not None:
            self.curated_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_file(self.curated_path, default='{"version": 2, "facts": []}\n')
        self.checkpoints_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.checkpoints_path, default="{}\n")
        self.embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.embeddings_path, default="")
        self._ensure_json_file(self.profile_path, self._default_profile())
        self._ensure_json_file(self.privacy_path, self._default_privacy())
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

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _default_profile(cls) -> dict[str, Any]:
        now_iso = cls._utcnow_iso()
        return {
            "communication_style": "balanced",
            "response_length_preference": "normal",
            "timezone": "UTC",
            "language": "pt-BR",
            "emotional_baseline": "neutral",
            "interests": [],
            "recurring_patterns": {},
            "upcoming_events": [],
            "learned_at": now_iso,
            "updated_at": now_iso,
        }

    @staticmethod
    def _default_privacy() -> dict[str, Any]:
        return {
            "never_memorize_patterns": ["senha", "cpf", "cartão", "token", "api_key"],
            "ephemeral_categories": ["context"],
            "ephemeral_ttl_days": 7,
            "encrypted_categories": [],
            "audit_log": True,
        }

    @classmethod
    def _ensure_json_file(cls, path: Path, default_payload: dict[str, Any]) -> None:
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8").strip()
                if raw:
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        return
            except Exception:
                pass
        path.write_text(json.dumps(default_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _load_json_dict(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                return dict(fallback)
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return dict(fallback)

    @staticmethod
    def _write_json_dict(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
            "category": str(row.get("category", "context") or "context"),
            "last_seen_at": last_seen_at,
            "mentions": max(1, mentions),
            "session_count": max(1, session_count),
            "sessions": sessions[-cls._MAX_CURATED_SESSIONS_PER_FACT :],
            "importance": max(0.1, importance),
        }

    @staticmethod
    def _run_coro_sync(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result: dict[str, Any] = {"value": None, "error": None}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if result["error"] is not None:
            raise result["error"]
        return result["value"]

    @staticmethod
    def _normalize_embedding(raw: Any) -> list[float] | None:
        if not isinstance(raw, list) or not raw:
            return None
        out: list[float] = []
        for item in raw:
            try:
                out.append(float(item))
            except Exception:
                return None
        return out if out else None

    @classmethod
    def _extract_embedding_from_response(cls, payload: Any) -> list[float] | None:
        data = getattr(payload, "data", None)
        if data is None and isinstance(payload, dict):
            data = payload.get("data")
        if not isinstance(data, list) or not data:
            return None
        first = data[0]
        embedding = None
        if isinstance(first, dict):
            embedding = first.get("embedding")
        else:
            embedding = getattr(first, "embedding", None)
        return cls._normalize_embedding(embedding)

    def _generate_embedding(self, text: str) -> list[float] | None:
        if not self.semantic_enabled:
            return None
        clean = str(text or "").strip()
        if not clean:
            return None
        try:
            import litellm  # type: ignore
        except Exception:
            return None

        for model_name in ("gemini/text-embedding-004", "openai/text-embedding-3-small"):
            try:
                response = self._run_coro_sync(
                    litellm.aembedding(
                        model=model_name,
                        input=[clean],
                    )
                )
                embedding = self._extract_embedding_from_response(response)
                if embedding is not None:
                    return embedding
            except Exception:
                continue
        return None

    @classmethod
    def _cosine_similarity(cls, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for idx in range(len(left)):
            lval = float(left[idx])
            rval = float(right[idx])
            dot += lval * rval
            left_norm += lval * lval
            right_norm += rval * rval
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return dot / math.sqrt(left_norm * right_norm)

    def _append_embedding(self, *, record_id: str, embedding: list[float], created_at: str, source: str) -> None:
        payload = {
            "id": str(record_id or ""),
            "embedding": embedding,
            "created_at": str(created_at or ""),
            "source": str(source or ""),
        }
        with self._locked_file(self.embeddings_path, "a", exclusive=True) as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            fh.flush()

    def _read_embeddings_map(self) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        with self._locked_file(self.embeddings_path, "r", exclusive=False) as fh:
            lines = fh.read().splitlines()
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            row_id = str(payload.get("id", "")).strip()
            if not row_id:
                continue
            embedding = self._normalize_embedding(payload.get("embedding"))
            if embedding is None:
                continue
            out[row_id] = embedding
        return out

    def _prune_embeddings_for_ids(self, removed_ids: set[str]) -> int:
        if not removed_ids:
            return 0
        removed = 0
        with self._locked_file(self.embeddings_path, "r+", exclusive=True) as fh:
            lines = fh.read().splitlines()
            kept_lines: list[str] = []
            for line in lines:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    kept_lines.append(raw)
                    continue
                if not isinstance(payload, dict):
                    kept_lines.append(raw)
                    continue
                row_id = str(payload.get("id", "")).strip()
                if row_id and row_id in removed_ids:
                    removed += 1
                    continue
                kept_lines.append(raw)

            fh.seek(0)
            fh.truncate()
            if kept_lines:
                fh.write("\n".join(kept_lines) + "\n")
            fh.flush()
        return removed

    def backfill_embeddings(self, *, limit: int | None = None) -> dict[str, int | bool]:
        total_rows = len(self.all()) + len(self.curated())
        if not self.semantic_enabled:
            return {
                "enabled": False,
                "total_records": total_rows,
                "processed": 0,
                "created": 0,
                "skipped_existing": 0,
                "failed": 0,
                "limit": max(1, int(limit)) if limit is not None else 0,
            }

        bounded_limit = max(1, int(limit)) if limit is not None else None
        records = self.curated() + self.all()
        seen_record_ids: set[str] = set()
        try:
            existing_embeddings = self._read_embeddings_map()
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)
            existing_embeddings = {}
        embedded_ids = set(existing_embeddings.keys())

        processed = 0
        created = 0
        skipped_existing = 0
        failed = 0

        for row in records:
            row_id = str(row.id or "").strip()
            if not row_id or row_id in seen_record_ids:
                continue
            seen_record_ids.add(row_id)
            if row_id in embedded_ids:
                skipped_existing += 1
                continue
            if bounded_limit is not None and created >= bounded_limit:
                break

            processed += 1
            try:
                embedding = self._generate_embedding(str(row.text or ""))
                if embedding is None:
                    failed += 1
                    continue
                self._append_embedding(
                    record_id=row_id,
                    embedding=embedding,
                    created_at=str(row.created_at or ""),
                    source=str(row.source or ""),
                )
                embedded_ids.add(row_id)
                created += 1
            except Exception as exc:
                self._diagnostics["last_error"] = str(exc)
                failed += 1

        return {
            "enabled": True,
            "total_records": len(seen_record_ids),
            "processed": processed,
            "created": created,
            "skipped_existing": skipped_existing,
            "failed": failed,
            "limit": bounded_limit or 0,
        }

    def _classify_category_with_llm(self, text: str) -> str | None:
        prompt = (
            "Classifique a memoria em UMA categoria desta lista: "
            "preferences, facts, decisions, skills, context, relationships. "
            "Retorne apenas o nome da categoria.\n\n"
            f"MEMORIA:\n{text.strip()}"
        )
        try:
            import litellm  # type: ignore

            response = self._run_coro_sync(
                litellm.acompletion(
                    model="gemini/gemini-2.5-flash",
                    temperature=0,
                    max_tokens=12,
                    messages=[
                        {"role": "system", "content": "Voce responde somente com uma categoria valida."},
                        {"role": "user", "content": prompt},
                    ],
                )
            )
            content = ""
            choices = getattr(response, "choices", None)
            if choices is None and isinstance(response, dict):
                choices = response.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                message = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
                if isinstance(message, dict):
                    content = str(message.get("content", "") or "")
                else:
                    content = str(getattr(message, "content", "") or "")
            candidate = content.strip().lower()
            if candidate in self._MEMORY_CATEGORIES:
                return candidate
            return None
        except Exception:
            return None

    def _heuristic_category(self, text: str, source: str) -> str:
        normalized = str(text or "").lower()
        source_norm = str(source or "").lower()
        if any(token in normalized for token in ("prefer", "preference", "always", "never", "gosto", "prefiro")):
            return "preferences"
        if any(token in normalized for token in ("decide", "decision", "we will", "vamos", "escolhemos", "resolved")):
            return "decisions"
        if any(token in normalized for token in ("can ", "how to", "skill", "know how", "sei ", "consigo")):
            return "skills"
        if any(token in normalized for token in ("name is", "works at", "friend", "wife", "husband", "team", "cliente", "parceiro")):
            return "relationships"
        if source_norm.startswith("curated:") or any(token in normalized for token in ("timezone", "deadline", "fact", "is ", "sao", "eh ")):
            return "facts"
        return "context"

    def _categorize_memory(self, text: str, source: str) -> str:
        if not self.memory_auto_categorize:
            return "context"
        by_llm = self._classify_category_with_llm(text)
        if by_llm in self._MEMORY_CATEGORIES:
            return by_llm
        return self._heuristic_category(text, source)

    @staticmethod
    def _detect_emotional_tone(text: str) -> str:
        raw_text = str(text or "")
        if not raw_text.strip():
            return "neutral"

        def _normalize_for_emotion(value: str) -> str:
            lowered = str(value or "").strip().lower()
            if not lowered:
                return ""
            normalized = unicodedata.normalize("NFKD", lowered)
            return "".join(ch for ch in normalized if not unicodedata.combining(ch))

        clean = _normalize_for_emotion(raw_text)
        best_label = "neutral"
        best_score = 0
        for label, markers in EMOTIONAL_MARKERS.items():
            score = 0
            for marker in markers:
                marker_clean = _normalize_for_emotion(marker)
                if marker_clean and marker_clean in clean:
                    score += 1
            if score > best_score:
                best_score = score
                best_label = label
        return best_label

    @staticmethod
    def _guidance_label_from_tone(tone: str) -> str:
        clean = str(tone or "").strip().lower()
        if clean in {"frustrated", "sad", "negative", "urgent"}:
            return "frustrated"
        if clean in {"excited", "positive"}:
            return "excited"
        return "neutral"

    def emotion_guidance(self, user_text: str, *, session_id: str = "") -> str:
        if not self.emotional_tracking:
            return ""

        current_tone = self._detect_emotional_tone(user_text)
        guidance_label = self._guidance_label_from_tone(current_tone)
        if guidance_label == "neutral":
            profile = self._load_json_dict(self.profile_path, self._default_profile())
            baseline = str(profile.get("emotional_baseline", "neutral") or "neutral")
            guidance_label = self._guidance_label_from_tone(baseline)

        if guidance_label == "frustrated":
            return "User seems frustrated. Be more empathetic and brief."
        if guidance_label == "excited":
            return "User is excited. Match the energy appropriately."
        return ""

    @staticmethod
    def _extract_timezone(text: str) -> str | None:
        clean = str(text or "").lower()
        if not clean:
            return None
        offset_match = re.search(r"\butc\s*([+-]\d{1,2})\b", clean)
        if offset_match:
            return f"UTC{offset_match.group(1)}"
        if "sao paulo" in clean or "são paulo" in clean or re.search(r"\bsp\b", clean):
            return "America/Sao_Paulo"
        return None

    @classmethod
    def _extract_topics(cls, text: str) -> list[str]:
        topics: list[str] = []
        for token in cls._tokens(text):
            if len(token) < 4:
                continue
            if token in PROFILE_TOPIC_STOPWORDS:
                continue
            if token.isdigit():
                continue
            if token not in topics:
                topics.append(token)
        return topics[:8]

    def _privacy_allows_memorize(self, text: str) -> bool:
        privacy = self._load_json_dict(self.privacy_path, self._default_privacy())
        patterns = privacy.get("never_memorize_patterns", [])
        if not isinstance(patterns, list):
            patterns = []
        lowered = str(text or "").lower()
        for item in patterns:
            pattern = str(item or "").strip().lower()
            if pattern and pattern in lowered:
                return False
        return True

    def _update_profile_from_text(self, text: str) -> None:
        clean = str(text or "").strip()
        if not clean:
            return
        profile = self._load_json_dict(self.profile_path, self._default_profile())
        changed = False
        lowered = clean.lower()

        if "prefiro respostas curtas" in lowered:
            if profile.get("response_length_preference") != "curto":
                profile["response_length_preference"] = "curto"
                changed = True

        timezone_value = self._extract_timezone(clean)
        if timezone_value and profile.get("timezone") != timezone_value:
            profile["timezone"] = timezone_value
            changed = True

        topics = self._extract_topics(clean)
        recurring_patterns = dict(profile.get("recurring_patterns", {}))
        if not isinstance(recurring_patterns, dict):
            recurring_patterns = {}
        interests = list(profile.get("interests", []))
        if not isinstance(interests, list):
            interests = []

        for topic in topics:
            topic_data = recurring_patterns.get(topic, {})
            if not isinstance(topic_data, dict):
                topic_data = {}
            previous_count = int(topic_data.get("count", 0) or 0)
            topic_data["count"] = previous_count + 1
            topic_data["last_seen"] = self._utcnow_iso()
            recurring_patterns[topic] = topic_data
            if topic_data["count"] >= 2 and topic not in interests:
                interests.append(topic)
                changed = True

        if recurring_patterns != profile.get("recurring_patterns"):
            profile["recurring_patterns"] = recurring_patterns
            changed = True
        if interests != profile.get("interests"):
            profile["interests"] = interests
            changed = True

        baseline = self._detect_emotional_tone(clean)
        if baseline != "neutral" and profile.get("emotional_baseline") != baseline:
            profile["emotional_baseline"] = baseline
            changed = True

        if changed:
            if not str(profile.get("learned_at", "")).strip():
                profile["learned_at"] = self._utcnow_iso()
            profile["updated_at"] = self._utcnow_iso()
            self._write_json_dict(self.profile_path, profile)

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

    @classmethod
    def _query_has_temporal_intent(cls, query: str) -> bool:
        tokens = set(cls._tokens(query))
        if tokens.intersection(cls._TEMPORAL_QUERY_TOKENS):
            return True
        return bool(cls._TEMPORAL_VALUE_RE.search(str(query or "")))

    @classmethod
    def _memory_has_temporal_markers(cls, text: str) -> bool:
        tokens = set(cls._tokens(text))
        if tokens.intersection(cls._TEMPORAL_MEMORY_TOKENS):
            return True
        return bool(cls._TEMPORAL_VALUE_RE.search(str(text or "")))

    @classmethod
    def _recency_score(cls, created_at: str, *, now: datetime | None = None) -> float:
        stamp = cls._parse_iso_timestamp(created_at)
        if stamp.year <= 1:
            return 0.0
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        ref_now = now or datetime.now(timezone.utc)
        age_seconds = max(0.0, float((ref_now - stamp).total_seconds()))
        half_life_seconds = cls._RECENCY_HALF_LIFE_HOURS * 3600.0
        if half_life_seconds <= 0.0:
            return 0.0
        score = cls._RECENCY_MAX_BOOST * math.exp(-age_seconds / half_life_seconds)
        return max(0.0, min(cls._RECENCY_MAX_BOOST, round(score, 6)))

    @classmethod
    def _memory_is_temporally_relevant(cls, text: str, created_at: str) -> bool:
        if cls._memory_has_temporal_markers(text):
            return True
        return cls._recency_score(created_at) >= cls._TEMPORAL_RECENCY_RELEVANCE_MIN

    def add(self, text: str, *, source: str = "user") -> MemoryRecord:
        clean = text.strip()
        if not clean:
            raise ValueError("memory text must not be empty")
        row = MemoryRecord(
            id=uuid.uuid4().hex,
            text=clean,
            source=source,
            created_at=datetime.now(timezone.utc).isoformat(),
            category=self._categorize_memory(clean, source),
            layer=MemoryLayer.ITEM.value,
            emotional_tone=self._detect_emotional_tone(clean) if self.emotional_tracking else "neutral",
        )
        with self._locked_file(self.history_path, "a", exclusive=True) as fh:
            fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
            fh.flush()
        embedding = self._generate_embedding(clean)
        if embedding is not None:
            try:
                self._append_embedding(
                    record_id=row.id,
                    embedding=embedding,
                    created_at=row.created_at,
                    source=row.source,
                )
            except Exception:
                pass
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
            row = self._record_from_payload(payload)
            if row is None:
                continue
            out.append(row)

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
                category=str(item.get("category", "context") or "context"),
                layer=self._normalize_layer(item.get("layer", MemoryLayer.ITEM.value)),
            )
            for item in rows
            if str(item.get("text", "")).strip()
        ]

    async def memorize(
        self,
        *,
        text: str | None = None,
        messages: Iterable[dict[str, str]] | None = None,
        source: str = "session",
    ) -> dict[str, Any]:
        if messages is not None:
            joined_text = "\n".join(str(item.get("content", "") or "") for item in messages if isinstance(item, dict))
            if joined_text and not self._privacy_allows_memorize(joined_text):
                return {"status": "skipped", "mode": "consolidate", "record": None}
            record = await asyncio.to_thread(self.consolidate, messages, source=source)
            if record is None:
                return {"status": "skipped", "mode": "consolidate", "record": None}
            self._update_profile_from_text(record.text)
            return {"status": "ok", "mode": "consolidate", "record": asdict(record)}

        clean = str(text or "").strip()
        if not clean:
            raise ValueError("text or messages is required")
        if not self._privacy_allows_memorize(clean):
            return {"status": "skipped", "mode": "add", "record": None}
        record = await asyncio.to_thread(self.add, clean, source=source)
        self._update_profile_from_text(clean)
        return {"status": "ok", "mode": "add", "record": asdict(record)}

    @staticmethod
    def _serialize_hit(row: MemoryRecord) -> dict[str, Any]:
        return {
            "id": str(row.id or ""),
            "text": str(row.text or ""),
            "source": str(row.source or ""),
            "created_at": str(row.created_at or ""),
            "category": str(row.category or "context"),
            "user_id": str(row.user_id or "default"),
            "layer": MemoryStore._normalize_layer(getattr(row, "layer", MemoryLayer.ITEM.value)),
            "modality": str(row.modality or "text"),
            "updated_at": str(row.updated_at or ""),
            "confidence": float(row.confidence),
            "decay_rate": float(row.decay_rate),
            "emotional_tone": str(row.emotional_tone or "neutral"),
        }

    def _refine_hits_with_llm(self, query: str, hits: list[dict[str, Any]]) -> str | None:
        if not hits:
            return ""
        prompt = (
            "Use os trechos de memoria abaixo para responder de forma objetiva. "
            "Se os trechos nao forem suficientes, diga isso explicitamente.\n\n"
            f"PERGUNTA:\n{query}\n\n"
            f"MEMORIAS:\n{json.dumps(hits, ensure_ascii=False)}"
        )
        try:
            import litellm  # type: ignore
        except Exception:
            return None
        try:
            response = self._run_coro_sync(
                litellm.acompletion(
                    model="gemini/gemini-2.5-flash",
                    temperature=0,
                    max_tokens=256,
                    messages=[
                        {"role": "system", "content": "Responda apenas com base na memoria fornecida."},
                        {"role": "user", "content": prompt},
                    ],
                )
            )
        except Exception:
            return None
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
        if isinstance(message, dict):
            content = str(message.get("content", "") or "")
        else:
            content = str(getattr(message, "content", "") or "")
        return content.strip()

    async def retrieve(self, query: str, *, limit: int = 5, method: str = "rag") -> dict[str, Any]:
        clean_query = str(query or "").strip()
        if not clean_query:
            raise ValueError("query is required")
        bounded_limit = max(1, int(limit or 1))
        records = await asyncio.to_thread(self.search, clean_query, limit=bounded_limit)
        hits = [self._serialize_hit(row) for row in records]

        rag_payload: dict[str, Any] = {
            "status": "ok",
            "method": "rag",
            "query": clean_query,
            "limit": bounded_limit,
            "count": len(hits),
            "hits": hits,
            "metadata": {"fallback_to_rag": False},
        }
        normalized_method = str(method or "rag").strip().lower()
        if normalized_method == "rag":
            return rag_payload
        if normalized_method != "llm":
            raise ValueError("method must be 'rag' or 'llm'")

        llm_answer = await asyncio.to_thread(self._refine_hits_with_llm, clean_query, hits)
        if llm_answer is None:
            rag_payload["method"] = "llm"
            rag_payload["metadata"] = {"fallback_to_rag": True}
            return rag_payload

        return {
            "status": "ok",
            "method": "llm",
            "query": clean_query,
            "limit": bounded_limit,
            "count": len(hits),
            "hits": hits,
            "answer": llm_answer,
            "metadata": {"fallback_to_rag": False},
        }

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        curated_rows = self._read_curated_facts()
        curated_records = [
            MemoryRecord(
                id=str(item.get("id", "")),
                text=str(item.get("text", "")).strip(),
                source=str(item.get("source", "curated")),
                created_at=str(item.get("created_at", "")),
                category=str(item.get("category", "context") or "context"),
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
        query_has_temporal_intent = self._query_has_temporal_intent(query)
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

        semantic_scores = [0.0 for _ in records]
        semantic_active = False
        if self.semantic_enabled:
            query_embedding = self._generate_embedding(query)
            if query_embedding is not None:
                embeddings = self._read_embeddings_map()
                if embeddings:
                    for idx, row in enumerate(records):
                        vector = embeddings.get(row.id)
                        if vector is None:
                            continue
                        semantic_scores[idx] = self._cosine_similarity(query_embedding, vector)
                    semantic_active = True

        # Primary key: lexical overlap with query terms.
        # Secondary key: BM25 or hybrid semantic score.
        scored: list[tuple[float, float, float, int]] = []
        for idx, toks in enumerate(corpus_tokens):
            overlap = len(qset.intersection(toks))
            curated_boost = 0.0
            if records[idx].source.startswith("curated:"):
                importance = curated_importance.get(records[idx].id, 1.0)
                mentions = curated_mentions.get(records[idx].id, 1)
                curated_boost = 0.75 + min(2.0, importance * 0.25) + min(1.0, mentions * 0.1)
            temporal_score = self._recency_score(records[idx].created_at)
            if query_has_temporal_intent:
                if self._memory_has_temporal_markers(records[idx].text):
                    temporal_score += self._TEMPORAL_INTENT_MATCH_BOOST
                else:
                    temporal_score -= self._TEMPORAL_INTENT_MISS_PENALTY

            ranking_score = bm25_scores[idx]
            tie_breaker = temporal_score
            if semantic_active:
                ranking_score = (
                    self._SEMANTIC_BM25_WEIGHT * bm25_scores[idx]
                    + self._SEMANTIC_VECTOR_WEIGHT * semantic_scores[idx]
                )
                tie_breaker = curated_boost + temporal_score
                scored.append((float(overlap), ranking_score, tie_breaker, idx))
            else:
                scored.append((float(overlap) + curated_boost, ranking_score, tie_breaker, idx))

        scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)

        picked: list[MemoryRecord] = []
        for overlap_score, relevance_score, _tie_breaker, idx in scored:
            if len(picked) >= limit:
                break
            if overlap_score <= 0 and relevance_score <= 0.0:
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

    @staticmethod
    def _normalize_prefix(value: str) -> str:
        clean = str(value or "").strip().lower()
        if clean.startswith("mem:"):
            clean = clean[4:]
        return clean

    @classmethod
    def _match_prefixes(cls, value: str, prefixes: set[str]) -> bool:
        normalized = cls._normalize_prefix(value)
        if not normalized:
            return False
        return any(normalized.startswith(prefix) for prefix in prefixes)

    @staticmethod
    def _record_sort_key(row: MemoryRecord) -> tuple[datetime, str]:
        return (MemoryStore._parse_iso_timestamp(str(row.created_at or "")), str(row.id or ""))

    def delete_by_prefixes(self, prefixes: Iterable[str], *, limit: int | None = None) -> dict[str, int | list[str]]:
        clean_prefixes = {
            self._normalize_prefix(prefix)
            for prefix in prefixes
            if self._normalize_prefix(prefix)
        }
        if not clean_prefixes:
            return {
                "deleted_ids": [],
                "history_deleted": 0,
                "curated_deleted": 0,
                "embeddings_deleted": 0,
                "deleted_count": 0,
            }

        bounded_limit = max(1, int(limit)) if limit is not None else None
        history_rows = self._read_history_records()
        curated_rows = self.curated()
        combined = history_rows + curated_rows
        combined.sort(key=self._record_sort_key, reverse=True)

        selected_ids: list[str] = []
        seen_ids: set[str] = set()
        for row in combined:
            row_id = str(row.id or "").strip()
            if not row_id or row_id in seen_ids:
                continue
            if not self._match_prefixes(row_id, clean_prefixes):
                continue
            seen_ids.add(row_id)
            selected_ids.append(row_id)
            if bounded_limit is not None and len(selected_ids) >= bounded_limit:
                break

        if not selected_ids:
            return {
                "deleted_ids": [],
                "history_deleted": 0,
                "curated_deleted": 0,
                "embeddings_deleted": 0,
                "deleted_count": 0,
            }

        selected_lookup = set(selected_ids)
        history_deleted = 0
        curated_deleted = 0
        embeddings_deleted = 0

        try:
            with self._locked_file(self.history_path, "r+", exclusive=True) as fh:
                lines = fh.read().splitlines()
                kept_lines: list[str] = []
                for line in lines:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        kept_lines.append(raw)
                        continue
                    if not isinstance(payload, dict):
                        kept_lines.append(raw)
                        continue
                    row_id = str(payload.get("id", "")).strip()
                    if row_id and row_id in selected_lookup:
                        history_deleted += 1
                        continue
                    kept_lines.append(raw)

                fh.seek(0)
                fh.truncate()
                if kept_lines:
                    fh.write("\n".join(kept_lines) + "\n")
                fh.flush()
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

        if self.curated_path is not None:
            try:
                facts = self._read_curated_facts()
                kept_facts: list[dict[str, object]] = []
                for fact in facts:
                    row_id = str(fact.get("id", "")).strip()
                    if row_id and row_id in selected_lookup:
                        curated_deleted += 1
                        continue
                    kept_facts.append(fact)
                self._write_curated_facts(kept_facts)
            except Exception as exc:
                self._diagnostics["last_error"] = str(exc)

        try:
            embeddings_deleted = self._prune_embeddings_for_ids(selected_lookup)
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

        deleted_ids = [rid for rid in selected_ids if rid in selected_lookup]
        return {
            "deleted_ids": deleted_ids,
            "history_deleted": history_deleted,
            "curated_deleted": curated_deleted,
            "embeddings_deleted": embeddings_deleted,
            "deleted_count": len(deleted_ids),
        }

    def export_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "exported_at": self._utcnow_iso(),
            "history": [asdict(row) for row in self.all()],
            "curated": [asdict(row) for row in self.curated()],
            "checkpoints": self._parse_checkpoints(self.checkpoints_path.read_text(encoding="utf-8")),
            "profile": self._load_json_dict(self.profile_path, self._default_profile()),
            "privacy": self._load_json_dict(self.privacy_path, self._default_privacy()),
        }

    def import_payload(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        history_rows = payload.get("history", [])
        curated_rows = payload.get("curated", [])
        checkpoints = payload.get("checkpoints", {})
        profile = payload.get("profile", {})
        privacy = payload.get("privacy", {})

        history_lines: list[str] = []
        if isinstance(history_rows, list):
            for row in history_rows:
                if not isinstance(row, dict):
                    continue
                parsed = self._record_from_payload(row)
                if parsed is None:
                    continue
                history_lines.append(json.dumps(asdict(parsed), ensure_ascii=False))
        with self._locked_file(self.history_path, "w", exclusive=True) as fh:
            if history_lines:
                fh.write("\n".join(history_lines) + "\n")
            fh.flush()

        if self.curated_path is not None and isinstance(curated_rows, list):
            facts = []
            for row in curated_rows:
                if isinstance(row, dict):
                    facts.append(row)
            self._write_curated_facts(facts)

        if isinstance(checkpoints, dict):
            with self._locked_file(self.checkpoints_path, "w", exclusive=True) as fh:
                fh.write(self._format_checkpoints(checkpoints))
                fh.flush()

        if isinstance(profile, dict):
            merged_profile = self._default_profile()
            merged_profile.update(profile)
            self._write_json_dict(self.profile_path, merged_profile)

        if isinstance(privacy, dict):
            merged_privacy = self._default_privacy()
            merged_privacy.update(privacy)
            self._write_json_dict(self.privacy_path, merged_privacy)

    def snapshot(self, tag: str = "") -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_tag = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(tag or "").strip()).strip("-")
        version_id = f"{stamp}-{safe_tag}" if safe_tag else stamp
        version_path = self.versions_path / f"{version_id}.json.gz"
        payload = self.export_payload()
        with gzip.open(version_path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        return version_id

    def rollback(self, version_id: str) -> None:
        clean = str(version_id or "").strip()
        if not clean:
            return
        version_path = self.versions_path / f"{clean}.json.gz"
        if not version_path.exists():
            raise FileNotFoundError(str(version_path))
        with gzip.open(version_path, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)
        self.import_payload(payload if isinstance(payload, dict) else {})

    def diff(self, version_a: str, version_b: str) -> dict[str, Any]:
        def _load_version(version_id: str) -> dict[str, Any]:
            path = self.versions_path / f"{version_id}.json.gz"
            if not path.exists():
                return {}
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                payload = json.load(fh)
            return payload if isinstance(payload, dict) else {}

        left = _load_version(version_a)
        right = _load_version(version_b)

        left_history = {
            str(item.get("id", "")): str(item.get("text", ""))
            for item in left.get("history", [])
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        }
        right_history = {
            str(item.get("id", "")): str(item.get("text", ""))
            for item in right.get("history", [])
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        }
        left_ids = set(left_history.keys())
        right_ids = set(right_history.keys())
        added_ids = sorted(right_ids - left_ids)
        removed_ids = sorted(left_ids - right_ids)
        changed_ids = sorted(
            row_id for row_id in left_ids.intersection(right_ids) if left_history.get(row_id) != right_history.get(row_id)
        )

        return {
            "added": {row_id: right_history[row_id] for row_id in added_ids},
            "removed": {row_id: left_history[row_id] for row_id in removed_ids},
            "changed": {
                row_id: {"from": left_history[row_id], "to": right_history[row_id]}
                for row_id in changed_ids
            },
            "counts": {
                "added": len(added_ids),
                "removed": len(removed_ids),
                "changed": len(changed_ids),
            },
        }

    def analysis_stats(self) -> dict[str, Any]:
        history_rows = self.all()
        curated_rows = self.curated()
        combined = history_rows + curated_rows
        record_ids = {
            str(row.id or "").strip()
            for row in combined
            if str(row.id or "").strip()
        }

        now = datetime.now(timezone.utc)
        cutoff_24h = now.timestamp() - (24 * 3600)
        cutoff_7d = now.timestamp() - (7 * 24 * 3600)
        cutoff_30d = now.timestamp() - (30 * 24 * 3600)

        last_24h = 0
        last_7d = 0
        last_30d = 0
        temporal_marked_count = 0
        sources: Counter[str] = Counter()
        categories: Counter[str] = Counter()

        for row in combined:
            text = str(row.text or "")
            created_at = self._parse_iso_timestamp(str(row.created_at or ""))
            created_ts = created_at.timestamp() if created_at.year > 1 else 0.0

            if created_ts >= cutoff_24h:
                last_24h += 1
            if created_ts >= cutoff_7d:
                last_7d += 1
            if created_ts >= cutoff_30d:
                last_30d += 1
            if self._memory_has_temporal_markers(text):
                temporal_marked_count += 1
            sources[str(row.source or "unknown")] += 1
            categories[str(getattr(row, "category", "context") or "context")] += 1

        top_sources = [
            {"source": source, "count": count}
            for source, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))[:8]
        ]

        try:
            embeddings = self._read_embeddings_map()
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)
            embeddings = {}
        embedded_records = len(record_ids.intersection(set(embeddings.keys())))
        total_records = len(record_ids)
        missing_records = max(0, total_records - embedded_records)
        coverage_ratio = float(1.0 if total_records == 0 else embedded_records / total_records)

        return {
            "counts": {
                "history": len(history_rows),
                "curated": len(curated_rows),
                "total": len(combined),
            },
            "recent": {
                "last_24h": last_24h,
                "last_7d": last_7d,
                "last_30d": last_30d,
            },
            "temporal_marked_count": temporal_marked_count,
            "top_sources": top_sources,
            "categories": {
                name: count
                for name, count in sorted(categories.items(), key=lambda item: (-item[1], item[0]))
            },
            "semantic": {
                "enabled": bool(self.semantic_enabled),
                "total_records": total_records,
                "embedded_records": embedded_records,
                "missing_records": missing_records,
                "coverage_ratio": round(coverage_ratio, 6),
                "coverage_percent": round(coverage_ratio * 100.0, 2),
            },
        }


# Backward-compatible API expected by legacy CLI.
def add_note(text: str) -> None:
    MemoryStore().add(text, source="legacy")


def search_notes(query: str, limit: int = 10) -> list[str]:
    return [row.text for row in MemoryStore().search(query, limit=limit)]
