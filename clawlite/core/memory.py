from __future__ import annotations

import json
import gzip
import hashlib
import base64
import hmac
import math
import os
import re
import asyncio
import secrets
import threading
import unicodedata
import uuid
import urllib.error
import urllib.request
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from html import unescape
from pathlib import Path
from typing import Any, Iterable

from clawlite.core.memory_backend import MemoryBackend, resolve_memory_backend

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
REASONING_LAYERS: tuple[str, ...] = ("fact", "hypothesis", "decision", "outcome")
REASONING_LAYER_SET: frozenset[str] = frozenset(REASONING_LAYERS)
# Memory type taxonomy (inspired by memU)
MEMORY_TYPE_PROFILE = "profile"      # User identity, preferences, roles
MEMORY_TYPE_EVENT = "event"          # Time-bound occurrences, interactions
MEMORY_TYPE_KNOWLEDGE = "knowledge"  # Facts, documentation, learned info
MEMORY_TYPE_BEHAVIOR = "behavior"    # Observed patterns, habits
MEMORY_TYPE_SKILL = "skill"          # Agent capabilities, learned procedures
MEMORY_TYPE_TOOL = "tool"            # Tool usage patterns, configs

MEMORY_TYPES: tuple[str, ...] = ("profile", "event", "knowledge", "behavior", "skill", "tool")
MEMORY_TYPE_SET: frozenset[str] = frozenset(MEMORY_TYPES)
MEMORY_TYPES_FROZENSET: frozenset[str] = frozenset({
    MEMORY_TYPE_PROFILE,
    MEMORY_TYPE_EVENT,
    MEMORY_TYPE_KNOWLEDGE,
    MEMORY_TYPE_BEHAVIOR,
    MEMORY_TYPE_SKILL,
    MEMORY_TYPE_TOOL,
})
RETRIEVAL_LIST_FILTER_KEYS: frozenset[str] = frozenset({"categories", "memory_types", "modalities", "sources"})
RETRIEVAL_DATE_FILTER_KEYS: frozenset[str] = frozenset({"created_after", "created_before", "happened_after", "happened_before"})
RETRIEVAL_FILTER_KEYS: frozenset[str] = RETRIEVAL_LIST_FILTER_KEYS.union(RETRIEVAL_DATE_FILTER_KEYS)
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


def compute_salience_score(
    *,
    similarity: float,
    updated_at: str,
    reinforcement_count: int = 0,
    now: "datetime.datetime | None" = None,
    decay_half_life_days: float = 30.0,
) -> float:
    """Compute a [0,1] salience score combining similarity, recency, and reinforcement.

    Formula: 0.5 * similarity + 0.3 * recency_decay + 0.2 * reinforcement_boost
    """
    import datetime as _datetime
    similarity = max(0.0, min(1.0, float(similarity or 0.0)))

    recency = 0.0
    if updated_at:
        try:
            dt = _datetime.datetime.fromisoformat(str(updated_at))
            if now is None:
                now = _datetime.datetime.now(_datetime.timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_datetime.timezone.utc)
            age_days = (now - dt).total_seconds() / 86400.0
            recency = math.exp(-math.log(2) * max(0.0, age_days) / max(1.0, decay_half_life_days))
        except Exception:
            recency = 0.5

    count = max(0, int(reinforcement_count or 0))
    reinforcement = math.log1p(count) / math.log1p(10)
    reinforcement = min(1.0, reinforcement)

    return 0.5 * similarity + 0.3 * recency + 0.2 * reinforcement


@dataclass(slots=True)
class MemoryRecord:
    id: str
    text: str
    source: str
    created_at: str
    category: str = "context"
    user_id: str = "default"
    layer: str = "item"
    reasoning_layer: str = "fact"
    modality: str = "text"
    updated_at: str = ""
    confidence: float = 1.0
    decay_rate: float = 0.0
    emotional_tone: str = "neutral"
    memory_type: str = "knowledge"
    happened_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryLayer(str, Enum):
    RESOURCE = "resource"
    ITEM = "item"
    CATEGORY = "category"


class MemoryStore:
    """Durable two-layer memory with optional history/curated split."""

    _PATH_LOCKS: dict[str, threading.RLock] = {}
    _PATH_LOCKS_GUARD = threading.Lock()
    _MAX_HISTORY_RECORDS = 2000
    _MAX_CURATED_FACTS = 250
    _MAX_CURATED_SESSIONS_PER_FACT = 12
    _MAX_CHECKPOINT_SOURCES = 4096
    _MAX_CHECKPOINT_SIGNATURES = 4096
    _MAX_QUALITY_HISTORY = 24
    _MAX_QUALITY_TUNING_RECENT_ACTIONS = 20
    _WORKING_MEMORY_MAX_MESSAGES_PER_SESSION = 24
    _WORKING_MEMORY_MAX_SESSIONS = 256
    _WORKING_MEMORY_PROMOTION_MIN_MESSAGES = 4
    _WORKING_MEMORY_PROMOTION_STEP = 4
    _WORKING_MEMORY_PROMOTION_WINDOW = 6
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
    _RANKING_CONFIDENCE_BOOST_MAX = 0.18
    _RANKING_REASONING_BOOST_MAX = 0.14
    _SALIENCE_MAX_BOOST = 0.55
    _SALIENCE_RECENCY_DECAY_DAYS = 30.0
    _DECAY_MAX_PENALTY = 0.55
    _UPCOMING_EVENT_MAX_BOOST = 0.35
    _ENTITY_MATCH_WEIGHTS: dict[str, float] = {
        "urls": 0.45,
        "emails": 0.35,
        "dates": 0.32,
        "times": 0.22,
    }
    _ENTITY_MATCH_MAX_BOOST = 0.65
    _MEMORY_CATEGORIES: tuple[str, ...] = (
        "preferences",
        "relationships",
        "knowledge",
        "context",
        "decisions",
        "skills",
        "events",
        "facts",
    )
    _TEXT_LIKE_SUFFIXES: frozenset[str] = frozenset({".txt", ".md", ".json", ".py", ".yaml", ".yml", ".csv", ".log"})
    _ENTITY_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
    _ENTITY_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
    _ENTITY_DATE_RE = re.compile(
        r"(?:\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b)",
        re.IGNORECASE,
    )
    _ENTITY_TIME_RE = re.compile(r"(?:\b\d{1,2}:\d{2}(?:\s?(?:am|pm))?\b|\b\d{1,2}\s?(?:am|pm)\b)", re.IGNORECASE)
    _WORKING_MEMORY_SHARE_SCOPE_SET: frozenset[str] = frozenset({"private", "parent", "family"})
    _RETRIEVAL_REWRITE_STOPWORDS: frozenset[str] = frozenset(
        {
            "what",
            "when",
            "where",
            "which",
            "who",
            "how",
            "tell",
            "me",
            "about",
            "please",
            "show",
            "find",
            "need",
            "know",
            "does",
            "do",
            "is",
            "are",
            "the",
            "a",
            "an",
            "o",
            "a",
            "os",
            "as",
            "de",
            "do",
            "da",
            "dos",
            "das",
            "sobre",
            "qual",
            "quais",
            "quando",
            "onde",
            "como",
            "me",
            "mostre",
            "preciso",
            "saber",
            "temos",
            "tem",
        }
    )

    @staticmethod
    def _normalize_layer(value: Any) -> str:
        if isinstance(value, MemoryLayer):
            return value.value
        normalized = str(value or "").strip().lower()
        if normalized in {MemoryLayer.RESOURCE.value, MemoryLayer.ITEM.value, MemoryLayer.CATEGORY.value}:
            return normalized
        return MemoryLayer.ITEM.value

    @staticmethod
    def _normalize_reasoning_layer(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in REASONING_LAYER_SET:
            return normalized
        return "fact"

    @staticmethod
    def _normalize_confidence(value: Any, *, default: float = 1.0) -> float:
        try:
            numeric = float(value)
        except Exception:
            numeric = default
        if not math.isfinite(numeric):
            return default
        return numeric

    @staticmethod
    def _normalize_decay_rate(value: Any, *, default: float = 0.0) -> float:
        try:
            numeric = float(value)
        except Exception:
            numeric = default
        if not math.isfinite(numeric):
            return default
        return max(0.0, min(0.5, numeric))

    @staticmethod
    def _normalize_memory_type(value: Any) -> str:
        clean = str(value or "").strip().lower()
        if clean in MEMORY_TYPE_SET:
            return clean
        return "knowledge"

    @classmethod
    def _default_decay_rate(cls, *, memory_type: str, category: str = "", happened_at: str = "") -> float:
        base_map = {
            "profile": 0.015,
            "behavior": 0.03,
            "skill": 0.04,
            "tool": 0.05,
            "knowledge": 0.08,
            "event": 0.12,
        }
        normalized_type = cls._normalize_memory_type(memory_type)
        normalized_category = str(category or "").strip().lower()
        base = float(base_map.get(normalized_type, 0.08))

        if normalized_category == "context":
            base += 0.03
        elif normalized_category in {"facts", "preferences"}:
            base = min(base, 0.03)

        if normalized_type == "event":
            stamp = cls._parse_iso_timestamp(str(happened_at or ""))
            if stamp.year > 1:
                now = datetime.now(timezone.utc)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                delta_days = float((stamp - now).total_seconds()) / 86400.0
                if delta_days >= 0.0:
                    if delta_days <= 30.0:
                        base = min(base, 0.035)
                    elif delta_days <= 180.0:
                        base = min(base, 0.06)
                elif abs(delta_days) >= 120.0:
                    base = max(base, 0.18)
        return cls._normalize_decay_rate(base, default=0.08)

    @classmethod
    def _normalize_metadata_value(cls, value: Any, *, depth: int = 0) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if depth >= 3:
            return str(value)
        if isinstance(value, dict):
            return cls._normalize_memory_metadata(value, depth=depth + 1)
        if isinstance(value, (list, tuple, set)):
            return [cls._normalize_metadata_value(item, depth=depth + 1) for item in list(value)[:32]]
        return str(value)

    @classmethod
    def _normalize_memory_metadata(cls, value: Any, *, depth: int = 0) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, Any] = {}
        for key, item in value.items():
            clean_key = str(key or "").strip()
            if not clean_key:
                continue
            out[clean_key] = cls._normalize_metadata_value(item, depth=depth)
        return out

    @classmethod
    def _normalize_source_sessions(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        clean_sessions: list[str] = []
        for item in value:
            session = cls._source_session_key(str(item or ""))
            if session and session not in clean_sessions:
                clean_sessions.append(session)
        return clean_sessions[-12:]

    @staticmethod
    def _metadata_content_hash(metadata: dict[str, Any] | None) -> str:
        if not isinstance(metadata, dict):
            return ""
        return str(metadata.get("content_hash", "") or "").strip()

    @classmethod
    def _metadata_reinforcement_count(cls, metadata: dict[str, Any] | None) -> int:
        if not isinstance(metadata, dict):
            return 1
        try:
            count = int(metadata.get("reinforcement_count", 1) or 1)
        except Exception:
            count = 1
        return max(1, count)

    @classmethod
    def _metadata_last_reinforced_at(cls, metadata: dict[str, Any] | None, *, fallback: str = "") -> str:
        if not isinstance(metadata, dict):
            return str(fallback or "")
        raw = str(metadata.get("last_reinforced_at", fallback) or fallback or "").strip()
        if raw and cls._parse_iso_timestamp(raw).year > 1:
            return raw
        return str(fallback or "")

    @staticmethod
    def _memory_scope_key(*, user_id: str, shared: bool) -> str:
        clean_user = MemoryStore._normalize_user_id(user_id)
        if shared:
            return f"shared:{clean_user}"
        return f"user:{clean_user}"

    @classmethod
    def _record_scope_key(cls, row: MemoryRecord) -> str:
        metadata = cls._normalize_memory_metadata(getattr(row, "metadata", {}))
        scope_key = str(metadata.get("scope_key", "") or "").strip()
        if scope_key:
            return scope_key
        return cls._memory_scope_key(user_id=str(getattr(row, "user_id", "default") or "default"), shared=False)

    @classmethod
    def _record_content_hash(cls, row: MemoryRecord) -> str:
        metadata_hash = cls._metadata_content_hash(getattr(row, "metadata", {}))
        if metadata_hash:
            return metadata_hash
        return cls._memory_content_hash(str(getattr(row, "text", "") or ""), cls._normalize_memory_type(getattr(row, "memory_type", "knowledge")))

    @classmethod
    def _seed_reinforcement_metadata(
        cls,
        metadata: dict[str, Any] | None,
        *,
        source: str,
        scope_key: str,
        reinforced_at: str,
    ) -> dict[str, Any]:
        prepared = cls._normalize_memory_metadata(metadata)
        prepared["scope_key"] = str(scope_key or "").strip()
        prepared["reinforcement_count"] = cls._metadata_reinforcement_count(prepared)
        prepared["last_reinforced_at"] = str(reinforced_at or "")
        source_session = cls._source_session_key(source)
        if source_session:
            existing_sessions = cls._normalize_source_sessions(prepared.get("source_sessions", []))
            if source_session not in existing_sessions:
                existing_sessions.append(source_session)
            prepared["source_session"] = source_session
            prepared["source_sessions"] = existing_sessions[-12:]
        return prepared

    @classmethod
    def _merge_reinforced_metadata(
        cls,
        current: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
        *,
        source: str,
        scope_key: str,
        reinforced_at: str,
    ) -> dict[str, Any]:
        current_metadata = cls._normalize_memory_metadata(current)
        incoming_metadata = cls._normalize_memory_metadata(incoming)
        merged = cls._normalize_memory_metadata({**current_metadata, **incoming_metadata})
        merged["scope_key"] = str(scope_key or "").strip()
        merged["content_hash"] = cls._metadata_content_hash(incoming_metadata) or cls._metadata_content_hash(current_metadata)
        merged["reinforcement_count"] = cls._metadata_reinforcement_count(current_metadata) + 1
        merged["last_reinforced_at"] = str(reinforced_at or "")
        source_session = cls._source_session_key(source)
        if source_session:
            sessions = cls._normalize_source_sessions(current_metadata.get("source_sessions", []))
            sessions.extend(cls._normalize_source_sessions(incoming_metadata.get("source_sessions", [])))
            if source_session not in sessions:
                sessions.append(source_session)
            merged["source_session"] = source_session
            merged["source_sessions"] = cls._normalize_source_sessions(sessions)
        return merged

    @classmethod
    def _salience_boost(cls, metadata: dict[str, Any] | None) -> float:
        reinforcement_count = cls._metadata_reinforcement_count(metadata)
        last_reinforced_at = cls._metadata_last_reinforced_at(metadata)
        reinforcement_factor = math.log(reinforcement_count + 1)

        if not last_reinforced_at:
            recency_factor = 0.5
        else:
            stamp = cls._parse_iso_timestamp(last_reinforced_at)
            if stamp.year <= 1:
                recency_factor = 0.5
            else:
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                days_ago = max(0.0, float((datetime.now(timezone.utc) - stamp).total_seconds()) / 86400.0)
                recency_factor = math.exp(-0.693 * days_ago / cls._SALIENCE_RECENCY_DECAY_DAYS)

        score = reinforcement_factor * recency_factor * 0.25
        return max(0.0, min(cls._SALIENCE_MAX_BOOST, round(score, 6)))

    @classmethod
    def _record_decay_anchor(cls, row: MemoryRecord) -> str:
        metadata = cls._normalize_memory_metadata(getattr(row, "metadata", {}))
        reinforced_at = cls._metadata_last_reinforced_at(metadata)
        if reinforced_at:
            return reinforced_at
        return str(getattr(row, "updated_at", "") or getattr(row, "created_at", "") or "")

    @classmethod
    def _decay_penalty(cls, row: MemoryRecord) -> float:
        decay_rate = cls._normalize_decay_rate(getattr(row, "decay_rate", 0.0), default=0.0)
        if decay_rate <= 0.0:
            return 0.0
        anchor = cls._parse_iso_timestamp(cls._record_decay_anchor(row))
        if anchor.year <= 1:
            return 0.0
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        age_days = max(0.0, float((datetime.now(timezone.utc) - anchor).total_seconds()) / 86400.0)
        if age_days <= 0.0:
            return 0.0
        penalty = cls._DECAY_MAX_PENALTY * (1.0 - math.exp(-(decay_rate * age_days) / 30.0))
        return max(0.0, min(cls._DECAY_MAX_PENALTY, round(penalty, 6)))

    @classmethod
    def _upcoming_event_boost(cls, row: MemoryRecord) -> float:
        if cls._normalize_memory_type(getattr(row, "memory_type", "knowledge")) != "event":
            return 0.0
        happened_at = cls._parse_iso_timestamp(str(getattr(row, "happened_at", "") or ""))
        if happened_at.year <= 1:
            return 0.0
        if happened_at.tzinfo is None:
            happened_at = happened_at.replace(tzinfo=timezone.utc)
        delta_days = float((happened_at - datetime.now(timezone.utc)).total_seconds()) / 86400.0
        if delta_days < -1.0:
            return 0.0
        if delta_days <= 30.0:
            score = cls._UPCOMING_EVENT_MAX_BOOST * math.exp(-max(0.0, delta_days) / 30.0)
            return max(0.0, min(cls._UPCOMING_EVENT_MAX_BOOST, round(score, 6)))
        if delta_days <= 180.0:
            score = (cls._UPCOMING_EVENT_MAX_BOOST * 0.45) * math.exp(-(delta_days - 30.0) / 120.0)
            return max(0.0, min(cls._UPCOMING_EVENT_MAX_BOOST * 0.45, round(score, 6)))
        return 0.0

    @classmethod
    def _bounded_confidence_score(cls, value: Any) -> float:
        normalized = cls._normalize_confidence(value, default=1.0)
        return max(0.0, min(1.0, normalized))

    @classmethod
    def _reasoning_intent_boosts(cls, query: str) -> dict[str, float]:
        tokens = set(cls._tokens(query))
        boosts = {layer: 0.0 for layer in REASONING_LAYERS}
        boosts["fact"] = 0.04

        if tokens.intersection({"hypothesis", "guess", "maybe", "assume", "possible", "possivel"}):
            boosts["hypothesis"] += 0.08
        if tokens.intersection({"decision", "decisions", "decide", "decided", "chosen", "choose", "escolha", "decisao"}):
            boosts["decision"] += 0.1
        if tokens.intersection({"outcome", "result", "results", "happened", "impact", "resultado", "efeito"}):
            boosts["outcome"] += 0.1

        if boosts["hypothesis"] == 0.0 and boosts["decision"] == 0.0 and boosts["outcome"] == 0.0:
            boosts["fact"] += 0.03

        max_boost = max(0.01, cls._RANKING_REASONING_BOOST_MAX)
        for key, value in list(boosts.items()):
            boosts[key] = max(0.0, min(max_boost, float(value)))
        return boosts

    @classmethod
    def _normalize_reasoning_layers_filter(cls, layers: Iterable[str] | None) -> set[str]:
        if layers is None:
            return set()
        normalized: set[str] = set()
        for item in layers:
            clean = cls._normalize_reasoning_layer(item)
            if clean in REASONING_LAYER_SET:
                normalized.add(clean)
        return normalized

    @staticmethod
    def _parse_required_iso_timestamp(value: Any, *, key: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError(f"retrieval filter '{key}' must be an ISO-8601 string")
        clean = value.strip()
        if not clean:
            raise ValueError(f"retrieval filter '{key}' must be an ISO-8601 string")
        parsed = MemoryStore._parse_iso_timestamp(clean)
        if parsed.year <= 1:
            raise ValueError(f"retrieval filter '{key}' must be an ISO-8601 string")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _parse_optional_iso_timestamp(value: str) -> datetime | None:
        clean = str(value or '').strip()
        if not clean:
            return None
        parsed = MemoryStore._parse_iso_timestamp(clean)
        if parsed.year <= 1:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @classmethod
    def _normalize_retrieval_filters(cls, filters: dict[str, Any] | None) -> dict[str, Any]:
        if filters is None:
            return {}
        if not isinstance(filters, dict):
            raise ValueError('filters must be a dict')

        unknown_keys = sorted(key for key in filters.keys() if str(key) not in RETRIEVAL_FILTER_KEYS)
        if unknown_keys:
            raise ValueError(f'unknown retrieval filter: {unknown_keys[0]}')

        normalized: dict[str, Any] = {}
        for key in sorted(filters.keys()):
            value = filters[key]
            if key in RETRIEVAL_LIST_FILTER_KEYS:
                if not isinstance(value, list):
                    raise ValueError(f"retrieval filter '{key}' must be a list of non-empty strings")
                deduped: list[str] = []
                seen: set[str] = set()
                for item in value:
                    if not isinstance(item, str):
                        raise ValueError(f"retrieval filter '{key}' must be a list of non-empty strings")
                    clean = item.strip().lower()
                    if not clean:
                        raise ValueError(f"retrieval filter '{key}' must be a list of non-empty strings")
                    if clean in seen:
                        continue
                    seen.add(clean)
                    deduped.append(clean)
                normalized[key] = tuple(deduped)
                continue
            normalized[key] = cls._parse_required_iso_timestamp(value, key=key)
        return normalized

    @classmethod
    def _record_matches_retrieval_filters(cls, row: MemoryRecord, filters: dict[str, Any]) -> bool:
        if not filters:
            return True

        for key, attr in (("categories", "category"), ("memory_types", "memory_type"), ("modalities", "modality"), ("sources", "source")):
            allowed = filters.get(key, ())
            if allowed and str(getattr(row, attr, '') or '').strip().lower() not in allowed:
                return False

        created_at = cls._parse_optional_iso_timestamp(str(getattr(row, 'created_at', '') or ''))
        created_after = filters.get('created_after')
        if created_after is not None and (created_at is None or created_at < created_after):
            return False
        created_before = filters.get('created_before')
        if created_before is not None and (created_at is None or created_at > created_before):
            return False

        happened_after = filters.get('happened_after')
        happened_before = filters.get('happened_before')
        if happened_after is not None or happened_before is not None:
            happened_at = cls._parse_optional_iso_timestamp(str(getattr(row, 'happened_at', '') or ''))
            if happened_at is None:
                return False
            if happened_after is not None and happened_at < happened_after:
                return False
            if happened_before is not None and happened_at > happened_before:
                return False

        return True

    @classmethod
    def _apply_retrieval_filters(cls, records: list[MemoryRecord], filters: dict[str, Any]) -> list[MemoryRecord]:
        if not filters:
            return records
        return [row for row in records if cls._record_matches_retrieval_filters(row, filters)]

    @classmethod
    def _record_from_payload(cls, payload: dict[str, Any]) -> MemoryRecord | None:
        text = str(payload.get("text", "")).strip()
        if not text:
            return None

        confidence = cls._normalize_confidence(payload.get("confidence", 1.0), default=1.0)
        decay_rate = cls._normalize_decay_rate(payload.get("decay_rate", payload.get("decayRate", 0.0)), default=0.0)

        return MemoryRecord(
            id=str(payload.get("id", "")),
            text=text,
            source=str(payload.get("source", "unknown")),
            created_at=str(payload.get("created_at", "")),
            category=str(payload.get("category", "context") or "context"),
            user_id=str(payload.get("user_id", payload.get("userId", "default")) or "default"),
            layer=cls._normalize_layer(payload.get("layer", "item")),
            reasoning_layer=cls._normalize_reasoning_layer(payload.get("reasoning_layer", payload.get("reasoningLayer", "fact"))),
            modality=str(payload.get("modality", "text") or "text"),
            updated_at=str(payload.get("updated_at", payload.get("updatedAt", "")) or ""),
            confidence=confidence,
            decay_rate=decay_rate,
            emotional_tone=str(payload.get("emotional_tone", payload.get("emotionalTone", "neutral")) or "neutral"),
            memory_type=cls._normalize_memory_type(payload.get("memory_type", payload.get("memoryType", "knowledge"))),
            happened_at=str(payload.get("happened_at", payload.get("happenedAt", "")) or ""),
            metadata=cls._normalize_memory_metadata(payload.get("metadata", {})),
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
        memory_backend_name: str = "sqlite",
        memory_backend_url: str = "",
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
        self.privacy_key_path = self.memory_home / "privacy.key"
        self.privacy_audit_path = self.memory_home / "privacy-audit.jsonl"
        self.versions_path = self.memory_home / "versions"
        self.users_path = self.memory_home / "users"
        self.shared_path = self.memory_home / "shared"
        self.shared_optin_path = self.shared_path / "optin.json"
        self.branches_meta_path = self.versions_path / "branches.json"
        self.branch_head_path = self.versions_path / "HEAD"
        self.profile_path = self.emotional_path / "profile.json"
        self._legacy_profile_path = self.memory_home / "profile.json"
        self.quality_state_path = self.memory_home / "quality-state.json"
        self.working_memory_path = self.memory_home / "working-memory.json"

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
        self.memory_backend_name = str(memory_backend_name or "sqlite").strip().lower() or "sqlite"
        self.memory_backend_url = str(memory_backend_url or "")
        self.backend: MemoryBackend = resolve_memory_backend(
            backend_name=self.memory_backend_name,
            pgvector_url=self.memory_backend_url,
        )

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
            self._atomic_write_text(self.profile_path, self._legacy_profile_path.read_text(encoding="utf-8"))

        if (not self._embeddings_path_explicit) and (not self.embeddings_path.exists()):
            legacy_embeddings_path = self.history_path.parent / "embeddings.jsonl"
            if legacy_embeddings_path != self.embeddings_path and legacy_embeddings_path.exists():
                self._atomic_write_text(self.embeddings_path, legacy_embeddings_path.read_text(encoding="utf-8"))

        self._ensure_file(self.history_path, default="")
        if self.curated_path is not None:
            self.curated_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_file(self.curated_path, default='{"version": 2, "facts": []}\n')
        self.checkpoints_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.checkpoints_path, default="{}\n")
        self.embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.embeddings_path, default="")
        self._ensure_json_file(self.profile_path, self._default_profile())
        self._ensure_json_file(self.quality_state_path, self._default_quality_state())
        self._ensure_json_file(self.working_memory_path, self._default_working_memory_state())
        self._ensure_json_file(self.privacy_path, self._default_privacy())
        self._ensure_json_file(self.shared_optin_path, {})
        self._ensure_file(self.privacy_audit_path, default="")
        self._ensure_json_file(self.branches_meta_path, self._default_branches_metadata())
        self._ensure_file(self.branch_head_path, default="main\n")
        self._sync_branch_head_file()
        self._diagnostics: dict[str, int | str] = {
            "history_read_corrupt_lines": 0,
            "history_repaired_files": 0,
            "consolidate_writes": 0,
            "consolidate_dedup_hits": 0,
            "reinforcement_hits": 0,
            "reinforcement_creates": 0,
            "session_recovery_attempts": 0,
            "session_recovery_hits": 0,
            "working_memory_promotions": 0,
            "working_memory_promotion_skips": 0,
            "privacy_audit_writes": 0,
            "privacy_audit_skipped": 0,
            "privacy_audit_errors": 0,
            "privacy_ttl_deleted": 0,
            "privacy_encrypt_events": 0,
            "privacy_encrypt_errors": 0,
            "privacy_decrypt_events": 0,
            "privacy_decrypt_errors": 0,
            "privacy_key_load_events": 0,
            "privacy_key_create_events": 0,
            "privacy_key_errors": 0,
            "last_error": "",
        }
        backend_name = str(getattr(self.backend, "name", self.memory_backend_name) or self.memory_backend_name)
        backend_supported = False
        backend_initialized = False
        backend_init_error = ""
        backend_driver = ""
        backend_connection_ok = False
        backend_vector_extension = False
        backend_vector_version = ""

        def _capture_backend_details() -> None:
            nonlocal backend_driver, backend_connection_ok, backend_vector_extension, backend_vector_version, backend_init_error
            details_fn = getattr(self.backend, "diagnostics", None)
            if not callable(details_fn):
                return
            try:
                details = details_fn()
            except Exception as exc:
                backend_init_error = backend_init_error or str(exc)
                self._diagnostics["last_error"] = str(exc)
                return
            if not isinstance(details, dict):
                return
            backend_driver = str(details.get("driver_name", "") or "")
            backend_connection_ok = bool(details.get("connection_ok", False))
            backend_vector_extension = bool(details.get("vector_extension", False))
            backend_vector_version = str(details.get("vector_version", "") or "")
            backend_init_error = backend_init_error or str(details.get("last_error", "") or "")

        try:
            backend_supported = bool(self.backend.is_supported())
        except Exception as exc:
            backend_init_error = str(exc)
            self._diagnostics["last_error"] = str(exc)
        _capture_backend_details()
        if backend_supported:
            try:
                self.backend.initialize(self.memory_home)
                backend_initialized = True
            except Exception as exc:
                backend_init_error = str(exc)
                self._diagnostics["last_error"] = str(exc)
            _capture_backend_details()
        self._backend_diagnostics: dict[str, bool | str] = {
            "backend_name": backend_name,
            "backend_supported": backend_supported,
            "backend_initialized": backend_initialized,
            "backend_init_error": backend_init_error,
            "backend_driver": backend_driver,
            "backend_connection_ok": backend_connection_ok,
            "backend_vector_extension": backend_vector_extension,
            "backend_vector_version": backend_vector_version,
        }
        self._privacy_key: bytes | None = None

    @staticmethod
    def _ensure_file(path: Path, *, default: str) -> None:
        if path.exists():
            return
        MemoryStore._atomic_write_text(path, default)

    @staticmethod
    def _flush_and_fsync(handle: Any) -> None:
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except Exception:
            pass

    @staticmethod
    def _fsync_parent_dir(path: Path) -> None:
        parent = path.parent
        try:
            dir_fd = os.open(str(parent), os.O_RDONLY)
        except Exception:
            return
        try:
            os.fsync(dir_fd)
        except Exception:
            pass
        finally:
            try:
                os.close(dir_fd)
            except Exception:
                pass

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8") as fh:
                fh.write(content)
                MemoryStore._flush_and_fsync(fh)
            os.replace(temp_path, path)
            MemoryStore._fsync_parent_dir(path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def _atomic_write_text_locked(self, path: Path, content: str) -> None:
        # On Windows, replacing an open target file raises WinError 5. The
        # POSIX flock path still benefits from holding the target open, but the
        # fallback path must avoid opening the destination during os.replace().
        if fcntl is None:
            with self._path_lock(path):
                self._atomic_write_text(path, content)
            return
        with self._locked_file(path, "a+", exclusive=True):
            self._atomic_write_text(path, content)

    @classmethod
    def _path_lock(cls, path: Path) -> threading.RLock:
        key = str(path.expanduser().resolve())
        with cls._PATH_LOCKS_GUARD:
            lock = cls._PATH_LOCKS.get(key)
            if lock is None:
                lock = threading.RLock()
                cls._PATH_LOCKS[key] = lock
            return lock

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
    def _default_branches_metadata(cls) -> dict[str, Any]:
        return {
            "current": "main",
            "branches": {
                "main": {
                    "head": "",
                    "created_at": cls._utcnow_iso(),
                    "updated_at": cls._utcnow_iso(),
                }
            },
        }

    @staticmethod
    def _default_quality_state() -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": "",
            "baseline": {},
            "current": {},
            "history": [],
            "tuning": MemoryStore._default_quality_tuning_state(),
        }

    @staticmethod
    def _default_quality_tuning_state() -> dict[str, Any]:
        return {
            "degrading_streak": 0,
            "last_action": "",
            "last_action_at": "",
            "last_action_status": "",
            "last_reason": "",
            "next_run_at": "",
            "last_run_at": "",
            "last_error": "",
            "recent_actions": [],
        }

    @staticmethod
    def _quality_float(value: Any, *, minimum: float = 0.0, maximum: float = 1.0, default: float = 0.0) -> float:
        try:
            raw = float(value)
        except Exception:
            raw = default
        return max(minimum, min(maximum, raw))

    @staticmethod
    def _quality_int(value: Any, *, minimum: int = 0, default: int = 0) -> int:
        try:
            raw = int(value)
        except Exception:
            raw = default
        return max(minimum, raw)

    @staticmethod
    def _quality_reasoning_layer_key(value: Any) -> str | None:
        clean = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "fact": "fact",
            "facts": "fact",
            "factual": "fact",
            "hypothesis": "hypothesis",
            "hypotheses": "hypothesis",
            "guess": "hypothesis",
            "decision": "decision",
            "decisions": "decision",
            "choice": "decision",
            "outcome": "outcome",
            "outcomes": "outcome",
            "result": "outcome",
            "results": "outcome",
        }
        mapped = aliases.get(clean)
        if mapped in REASONING_LAYER_SET:
            return mapped
        return None

    @classmethod
    def _quality_reasoning_metrics_payload(cls, raw: Any) -> dict[str, Any]:
        payload = dict(raw) if isinstance(raw, dict) else {}

        layer_candidates: list[dict[str, Any]] = []
        for key in ("reasoning_layers", "reasoningLayers", "layers", "distribution"):
            value = payload.get(key)
            if isinstance(value, dict):
                layer_candidates.append(value)
        layer_candidates.append(payload)

        counts: dict[str, int] = {layer: 0 for layer in REASONING_LAYERS}
        for candidate in layer_candidates:
            for key, value in candidate.items():
                mapped = cls._quality_reasoning_layer_key(key)
                if mapped is None:
                    continue
                counts[mapped] = cls._quality_int(value)

        sum_counts = sum(int(value) for value in counts.values())
        total_records = cls._quality_int(
            payload.get("total_records", payload.get("totalRecords", payload.get("records_total", sum_counts))),
            default=sum_counts,
        )
        if total_records < sum_counts:
            total_records = sum_counts

        confidence_payload = payload.get("confidence", payload.get("conf", payload.get("confidence_summary", {})))
        confidence_raw = confidence_payload if isinstance(confidence_payload, dict) else {}
        confidence_average = cls._quality_float(
            confidence_raw.get("average", confidence_raw.get("avg", confidence_raw.get("mean", 0.0))),
            default=0.0,
        )
        confidence_minimum = cls._quality_float(
            confidence_raw.get("minimum", confidence_raw.get("min", 0.0)),
            default=0.0,
        )
        confidence_maximum = cls._quality_float(
            confidence_raw.get("maximum", confidence_raw.get("max", 0.0)),
            default=0.0,
        )
        confidence_has_any = any(
            key in confidence_raw for key in ("average", "avg", "mean", "minimum", "min", "maximum", "max")
        )

        distribution: dict[str, dict[str, float | int]] = {}
        for layer in REASONING_LAYERS:
            count = int(counts.get(layer, 0))
            ratio = (float(count) / float(total_records)) if total_records else 0.0
            distribution[layer] = {"count": count, "ratio": round(max(0.0, min(1.0, ratio)), 6)}

        weakest_layer = min(REASONING_LAYERS, key=lambda layer: (int(counts.get(layer, 0)), REASONING_LAYERS.index(layer)))
        weakest_ratio = float(distribution[weakest_layer]["ratio"])

        if total_records:
            expected = 1.0 / float(len(REASONING_LAYERS))
            divergence = sum(abs(float(distribution[layer]["ratio"]) - expected) for layer in REASONING_LAYERS)
            max_divergence = 2.0 * (1.0 - expected)
            balance_score = 1.0 - (divergence / max_divergence if max_divergence > 0 else 0.0)
        else:
            balance_score = 0.0
        balance_score = round(max(0.0, min(1.0, balance_score)), 6)

        provided = bool(payload)
        has_distribution_signal = total_records > 0
        return {
            "provided": provided,
            "has_distribution_signal": has_distribution_signal,
            "has_confidence_signal": confidence_has_any,
            "total_records": int(total_records),
            "distribution": distribution,
            "balance_score": balance_score,
            "weakest_layer": weakest_layer,
            "weakest_ratio": round(max(0.0, min(1.0, weakest_ratio)), 6),
            "confidence": {
                "average": round(confidence_average, 6),
                "minimum": round(confidence_minimum, 6),
                "maximum": round(confidence_maximum, 6),
            },
        }

    def quality_state_snapshot(self) -> dict[str, Any]:
        payload = self._load_json_dict(self.quality_state_path, self._default_quality_state())
        history_raw = payload.get("history", [])
        history = history_raw if isinstance(history_raw, list) else []
        baseline = payload.get("baseline", {}) if isinstance(payload.get("baseline", {}), dict) else {}
        current = payload.get("current", {}) if isinstance(payload.get("current", {}), dict) else {}
        tuning = self._normalize_quality_tuning_state(payload.get("tuning", {}))
        return {
            "version": 1,
            "updated_at": str(payload.get("updated_at", "") or ""),
            "baseline": baseline,
            "current": current,
            "history": history,
            "tuning": tuning,
        }

    @staticmethod
    def _quality_mode_from_state(score: int, drift: str, degrading_streak: int, last_error: str, *, has_report: bool) -> tuple[str, str]:
        if not has_report:
            return "normal", "quality_state_uninitialized"

        drift_clean = str(drift or "").strip().lower()
        has_error = bool(str(last_error or "").strip())
        if has_error:
            return "severe", "quality_tuning_error"
        if score <= 40 or degrading_streak >= 4:
            return "severe", "quality_score_or_streak_critical"
        if drift_clean == "degrading" and (degrading_streak >= 3 or score <= 55):
            return "severe", "quality_drift_critical"
        if score <= 70 or degrading_streak >= 2 or drift_clean == "degrading":
            return "degraded", "quality_drift_or_score_warning"
        return "normal", "quality_stable"

    @staticmethod
    def _integration_actor_class(actor: str) -> str:
        clean = str(actor or "").strip().lower()
        if clean in {"system", "gateway", "supervisor", "control", "runtime", "ops", "operator", "admin"}:
            return "privileged"
        if clean in {"subagent", "delegate", "worker", "tool", "skill", "executor"} or "subagent" in clean:
            return "delegated"
        if clean in {"agent", "assistant", "planner", "default"}:
            return "worker"
        return "worker"

    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        snapshot = self.quality_state_snapshot()
        current = snapshot.get("current", {}) if isinstance(snapshot.get("current", {}), dict) else {}
        tuning = snapshot.get("tuning", {}) if isinstance(snapshot.get("tuning", {}), dict) else {}
        drift_payload = current.get("drift", {}) if isinstance(current.get("drift", {}), dict) else {}

        has_report = bool(current) and "score" in current
        score = self._quality_int(current.get("score", 100 if not has_report else 0), minimum=0, default=100 if not has_report else 0)
        if score > 100:
            score = 100
        degrading_streak = self._quality_int(tuning.get("degrading_streak", 0), minimum=0, default=0)
        drift = str(drift_payload.get("assessment", "baseline" if not has_report else "stable") or "")
        last_error = str(tuning.get("last_error", "") or "")
        mode, reason = self._quality_mode_from_state(
            score,
            drift,
            degrading_streak,
            last_error,
            has_report=has_report,
        )

        actor_clean = str(actor or "default").strip() or "default"
        actor_class = self._integration_actor_class(actor_clean)

        if mode == "severe":
            allow_memory_write = False
            allow_skill_exec = False
            allow_subagent_spawn = False
            recommended_search_limit = 2
        elif mode == "degraded":
            allow_memory_write = True
            allow_skill_exec = actor_class == "privileged"
            allow_subagent_spawn = actor_class == "privileged"
            recommended_search_limit = 4
        else:
            allow_memory_write = True
            allow_skill_exec = True
            allow_subagent_spawn = actor_class != "delegated"
            recommended_search_limit = 8

        if actor_class == "delegated":
            allow_subagent_spawn = False
            recommended_search_limit = max(1, recommended_search_limit - 1)
            if mode != "normal":
                allow_skill_exec = False
                allow_memory_write = False if mode == "severe" else allow_memory_write

        quality_summary = {
            "score": score,
            "drift": drift,
            "degrading_streak": degrading_streak,
            "last_error": last_error,
            "updated_at": str(snapshot.get("updated_at", "") or ""),
            "has_report": has_report,
        }
        return {
            "actor": actor_clean,
            "actor_class": actor_class,
            "session_id": str(session_id or ""),
            "mode": mode,
            "reason": reason,
            "quality": quality_summary,
            "allow_memory_write": bool(allow_memory_write),
            "allow_skill_exec": bool(allow_skill_exec),
            "allow_subagent_spawn": bool(allow_subagent_spawn),
            "recommended_search_limit": int(recommended_search_limit),
        }

    def integration_policies_snapshot(self, *, session_id: str = "") -> dict[str, Any]:
        actors = ("system", "agent", "subagent", "tool")
        policies = {name: self.integration_policy(name, session_id=session_id) for name in actors}
        mode = "normal"
        rank = {"normal": 0, "degraded": 1, "severe": 2}
        for payload in policies.values():
            candidate = str(payload.get("mode", "normal") or "normal")
            if rank.get(candidate, 0) > rank.get(mode, 0):
                mode = candidate
        return {
            "session_id": str(session_id or ""),
            "mode": mode,
            "quality": policies["agent"].get("quality", {}),
            "policies": policies,
        }

    def integration_hint(self, actor: str, *, session_id: str = "") -> str:
        policy = self.integration_policy(actor, session_id=session_id)
        mode = str(policy.get("mode", "normal") or "normal")
        if mode == "normal":
            return ""
        if mode == "severe":
            return (
                "Memory quality is severe; avoid writes, skip skill/subagent actions, "
                "and prefer minimal retrieval while stabilization runs."
            )
        return (
            "Memory quality is degraded; keep retrieval focused and avoid expensive "
            "delegation unless strictly necessary."
        )

    def profile_prompt_hint(self) -> str:
        profile = self._load_json_dict(self.profile_path, self._default_profile())
        if not isinstance(profile, dict):
            return ""

        defaults = self._default_profile()
        lines: list[str] = []

        response_length = str(profile.get("response_length_preference", defaults.get("response_length_preference", "normal")) or "").strip()
        if response_length and response_length != str(defaults.get("response_length_preference", "normal")):
            lines.append(f"- Preferred response length: {response_length}")

        timezone_value = str(profile.get("timezone", defaults.get("timezone", "UTC")) or "").strip()
        if timezone_value and timezone_value != str(defaults.get("timezone", "UTC")):
            lines.append(f"- Timezone: {timezone_value}")

        language = str(profile.get("language", defaults.get("language", "pt-BR")) or "").strip()
        if language and language != str(defaults.get("language", "pt-BR")):
            lines.append(f"- Preferred language: {language}")

        emotional_baseline = str(profile.get("emotional_baseline", defaults.get("emotional_baseline", "neutral")) or "").strip()
        if emotional_baseline and emotional_baseline != str(defaults.get("emotional_baseline", "neutral")):
            lines.append(f"- Emotional baseline: {emotional_baseline}")

        interests_raw = profile.get("interests", [])
        interests = [str(item).strip() for item in interests_raw if str(item).strip()] if isinstance(interests_raw, list) else []
        if interests:
            lines.append(f"- Recurring interests: {', '.join(interests[:5])}")

        upcoming_raw = profile.get("upcoming_events", [])
        if isinstance(upcoming_raw, list):
            formatted: list[str] = []
            now = datetime.now(timezone.utc)
            for item in upcoming_raw[:3]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "") or "").strip()
                happened_at = str(item.get("happened_at", "") or "").strip()
                stamp = self._parse_iso_timestamp(happened_at)
                if not title or stamp.year <= 1:
                    continue
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp < now - timedelta(days=1):
                    continue
                formatted.append(f"{stamp.date().isoformat()} {title[:80]}")
            if formatted:
                lines.append(f"- Upcoming events: {'; '.join(formatted)}")

        if not lines:
            return ""

        return "\n".join(
            [
                "[User Profile]",
                *lines,
                "- Apply these preferences when relevant, without repeating them unless useful.",
            ]
        )

    def _normalize_quality_tuning_state(self, raw: Any) -> dict[str, Any]:
        payload = dict(raw) if isinstance(raw, dict) else {}
        defaults = self._default_quality_tuning_state()
        recent_actions_raw = payload.get("recent_actions", payload.get("recentActions", defaults["recent_actions"]))
        if not isinstance(recent_actions_raw, list):
            recent_actions_raw = []

        normalized_recent_actions: list[dict[str, Any]] = []
        for row in recent_actions_raw:
            if isinstance(row, dict):
                entry = dict(row)
                for key in ("action", "status", "reason", "at"):
                    if key in entry:
                        entry[key] = str(entry.get(key, "") or "")
                normalized_recent_actions.append(entry)
            elif row is not None:
                normalized_recent_actions.append({"action": str(row)})

        return {
            "degrading_streak": self._quality_int(payload.get("degrading_streak", defaults["degrading_streak"])),
            "last_action": str(payload.get("last_action", defaults["last_action"]) or ""),
            "last_action_at": str(payload.get("last_action_at", defaults["last_action_at"]) or ""),
            "last_action_status": str(payload.get("last_action_status", defaults["last_action_status"]) or ""),
            "last_reason": str(payload.get("last_reason", defaults["last_reason"]) or ""),
            "next_run_at": str(payload.get("next_run_at", defaults["next_run_at"]) or ""),
            "last_run_at": str(payload.get("last_run_at", defaults["last_run_at"]) or ""),
            "last_error": str(payload.get("last_error", defaults["last_error"]) or ""),
            "recent_actions": normalized_recent_actions[-self._MAX_QUALITY_TUNING_RECENT_ACTIONS :],
        }

    def _merge_quality_tuning_state(self, current: Any, patch: Any) -> dict[str, Any]:
        merged = self._normalize_quality_tuning_state(current)
        payload = dict(patch) if isinstance(patch, dict) else {}
        if not payload:
            return merged

        for key in (
            "degrading_streak",
            "last_action",
            "last_action_at",
            "last_action_status",
            "last_reason",
            "next_run_at",
            "last_run_at",
            "last_error",
        ):
            if key not in payload:
                continue
            if key == "degrading_streak":
                merged[key] = self._quality_int(payload.get(key), minimum=0, default=int(merged.get(key, 0) or 0))
            else:
                merged[key] = str(payload.get(key, "") or "")

        if "recentActions" in payload and "recent_actions" not in payload:
            recent_patch_raw = payload.get("recentActions")
        else:
            recent_patch_raw = payload.get("recent_actions")

        if isinstance(recent_patch_raw, list):
            merged["recent_actions"] = self._normalize_quality_tuning_state(
                {"recent_actions": list(merged.get("recent_actions", [])) + list(recent_patch_raw)}
            )["recent_actions"]
        elif isinstance(recent_patch_raw, dict):
            merged["recent_actions"] = self._normalize_quality_tuning_state(
                {"recent_actions": list(merged.get("recent_actions", [])) + [recent_patch_raw]}
            )["recent_actions"]

        return merged

    def update_quality_tuning_state(self, tuning_patch: dict[str, Any] | None = None) -> dict[str, Any]:
        previous_state = self.quality_state_snapshot()
        tuning = self._merge_quality_tuning_state(previous_state.get("tuning", {}), tuning_patch)
        updated_at = str(previous_state.get("updated_at", "") or self._utcnow_iso())
        if isinstance(tuning_patch, dict) and tuning_patch:
            updated_at = self._utcnow_iso()

        state = {
            "version": 1,
            "updated_at": updated_at,
            "baseline": previous_state.get("baseline", {}),
            "current": previous_state.get("current", {}),
            "history": previous_state.get("history", []),
            "tuning": tuning,
        }
        self._atomic_write_text_locked(
            self.quality_state_path,
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return tuning

    def update_quality_state(
        self,
        *,
        retrieval_metrics: dict[str, Any] | None = None,
        turn_stability_metrics: dict[str, Any] | None = None,
        semantic_metrics: dict[str, Any] | None = None,
        reasoning_layer_metrics: dict[str, Any] | None = None,
        gateway_metrics: dict[str, Any] | None = None,
        sampled_at: str = "",
        tuning_patch: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous_state = self.quality_state_snapshot()
        previous = previous_state.get("current", {}) if isinstance(previous_state.get("current", {}), dict) else {}

        retrieval_raw = retrieval_metrics if isinstance(retrieval_metrics, dict) else {}
        turn_raw = turn_stability_metrics if isinstance(turn_stability_metrics, dict) else {}
        semantic_raw = semantic_metrics if isinstance(semantic_metrics, dict) else {}
        reasoning_raw = reasoning_layer_metrics if isinstance(reasoning_layer_metrics, dict) else {}

        attempts = self._quality_int(retrieval_raw.get("attempts"))
        hits = self._quality_int(retrieval_raw.get("hits"))
        rewrites = self._quality_int(retrieval_raw.get("rewrites"))
        if hits > attempts:
            hits = attempts
        hit_rate = self._quality_float((float(hits) / float(attempts)) if attempts else retrieval_raw.get("hit_rate", 0.0))

        turn_successes = self._quality_int(turn_raw.get("successes"))
        turn_errors = self._quality_int(turn_raw.get("errors"))
        turn_total = turn_successes + turn_errors
        success_rate = self._quality_float(
            (float(turn_successes) / float(turn_total)) if turn_total else turn_raw.get("success_rate", 1.0),
            default=1.0,
        )
        error_rate = self._quality_float(1.0 - success_rate)

        semantic_coverage = self._quality_float(semantic_raw.get("coverage_ratio", 0.0))
        reasoning_payload = self._quality_reasoning_metrics_payload(reasoning_raw)

        reasoning_present = bool(
            reasoning_payload["provided"]
            and (reasoning_payload["has_distribution_signal"] or reasoning_payload["has_confidence_signal"])
        )
        confidence_average = float(reasoning_payload["confidence"]["average"])
        if not bool(reasoning_payload["has_confidence_signal"]):
            confidence_average = 0.5
        balance_score = float(reasoning_payload["balance_score"])
        weakest_ratio = float(reasoning_payload["weakest_ratio"])
        imbalance_penalty = 0.0
        if reasoning_present and weakest_ratio < 0.12:
            imbalance_penalty = min(1.0, (0.12 - weakest_ratio) / 0.12)

        reasoning_adjustment = 0.0
        if reasoning_present:
            reasoning_adjustment = ((balance_score - 0.5) * 3.0) + ((confidence_average - 0.5) * 3.0) - (imbalance_penalty * 2.0)
            reasoning_adjustment = max(-6.0, min(6.0, reasoning_adjustment))

        score_float = (hit_rate * 55.0) + (success_rate * 30.0) + (semantic_coverage * 15.0) + reasoning_adjustment
        score = self._quality_int(round(score_float), minimum=0)
        if score > 100:
            score = 100

        previous_score = self._quality_int(previous.get("score", 0))
        previous_hit_rate = self._quality_float(previous.get("retrieval", {}).get("hit_rate", 0.0)) if isinstance(previous.get("retrieval", {}), dict) else 0.0

        baseline_payload = previous_state.get("baseline", {}) if isinstance(previous_state.get("baseline", {}), dict) else {}
        baseline_score = self._quality_int(baseline_payload.get("score", score), default=score)
        baseline_hit_rate = (
            self._quality_float(baseline_payload.get("retrieval", {}).get("hit_rate", hit_rate))
            if isinstance(baseline_payload.get("retrieval", {}), dict)
            else hit_rate
        )

        score_delta_prev = score - previous_score
        score_delta_baseline = score - baseline_score
        hit_rate_delta_prev = round(hit_rate - previous_hit_rate, 6)
        hit_rate_delta_baseline = round(hit_rate - baseline_hit_rate, 6)

        previous_reasoning = previous.get("reasoning_layers", {}) if isinstance(previous.get("reasoning_layers", {}), dict) else {}
        previous_balance = self._quality_float(previous_reasoning.get("balance_score", balance_score), default=balance_score)
        previous_confidence_payload = previous_reasoning.get("confidence", {}) if isinstance(previous_reasoning.get("confidence", {}), dict) else {}
        previous_confidence_average = self._quality_float(
            previous_confidence_payload.get("average", confidence_average),
            default=confidence_average,
        )
        previous_weakest_ratio = self._quality_float(previous_reasoning.get("weakest_ratio", weakest_ratio), default=weakest_ratio)

        reasoning_balance_delta = round(balance_score - previous_balance, 6) if reasoning_present and bool(previous) else 0.0
        reasoning_confidence_delta = (
            round(confidence_average - previous_confidence_average, 6) if reasoning_present and bool(previous) else 0.0
        )
        reasoning_weakest_ratio_delta = (
            round(weakest_ratio - previous_weakest_ratio, 6) if reasoning_present and bool(previous) else 0.0
        )

        reasoning_degrading = bool(
            reasoning_present
            and bool(previous)
            and (
                reasoning_balance_delta <= -0.1
                or reasoning_confidence_delta <= -0.12
                or reasoning_weakest_ratio_delta <= -0.1
            )
        )
        reasoning_improving = bool(
            reasoning_present
            and bool(previous)
            and reasoning_balance_delta >= 0.1
            and reasoning_confidence_delta >= 0.08
            and reasoning_weakest_ratio_delta >= 0.08
        )

        if previous:
            score_degrading_threshold = -4 if reasoning_present else -5
            score_improving_threshold = 4 if reasoning_present else 5
            if score_delta_prev <= score_degrading_threshold or hit_rate_delta_prev <= -0.08 or reasoning_degrading:
                drift_assessment = "degrading"
            elif score_delta_prev >= score_improving_threshold or hit_rate_delta_prev >= 0.08 or reasoning_improving:
                drift_assessment = "improving"
            else:
                drift_assessment = "stable"
        else:
            drift_assessment = "baseline"

        recommendations: list[str] = []
        if attempts < 5:
            recommendations.append("Increase retrieval sample size to reduce score variance.")
        if hit_rate < 0.7:
            recommendations.append("Improve retrieval hit rate with stronger memory curation and query rewrites.")
        if error_rate > 0.2:
            recommendations.append("Reduce turn error rate by investigating recent memory and privacy failures.")
        if bool(semantic_raw.get("enabled", False)) and semantic_coverage < 0.6:
            recommendations.append("Run semantic embedding backfill to improve retrieval coverage.")
        if reasoning_present and weakest_ratio < 0.15:
            recommendations.append(
                f"Strengthen {reasoning_payload['weakest_layer']} reasoning coverage to rebalance memory quality signals."
            )
        if reasoning_present and balance_score < 0.65:
            recommendations.append("Rebalance reasoning layers by increasing underrepresented records in recent sessions.")
        if reasoning_present and confidence_average < 0.6:
            recommendations.append("Raise confidence quality by validating uncertain memories before promotion.")
        if drift_assessment == "degrading":
            recommendations.append("Quality drift detected; review memory diagnostics and recent regressions.")
        if not recommendations:
            recommendations.append("Quality is stable; continue monitoring and periodic memory snapshots.")

        report = {
            "sampled_at": str(sampled_at or self._utcnow_iso()),
            "score": score,
            "retrieval": {
                "attempts": attempts,
                "hits": hits,
                "rewrites": rewrites,
                "hit_rate": round(hit_rate, 6),
            },
            "turn_stability": {
                "successes": turn_successes,
                "errors": turn_errors,
                "success_rate": round(success_rate, 6),
                "error_rate": round(error_rate, 6),
            },
            "drift": {
                "assessment": drift_assessment,
                "score_delta_previous": score_delta_prev,
                "score_delta_baseline": score_delta_baseline,
                "hit_rate_delta_previous": hit_rate_delta_prev,
                "hit_rate_delta_baseline": hit_rate_delta_baseline,
                "reasoning_balance_delta_previous": reasoning_balance_delta,
                "reasoning_confidence_delta_previous": reasoning_confidence_delta,
                "reasoning_weakest_ratio_delta_previous": reasoning_weakest_ratio_delta,
            },
            "semantic": {
                "enabled": bool(semantic_raw.get("enabled", False)),
                "coverage_ratio": round(semantic_coverage, 6),
            },
            "reasoning_layers": {
                "total_records": int(reasoning_payload["total_records"]),
                "distribution": reasoning_payload["distribution"],
                "balance_score": float(reasoning_payload["balance_score"]),
                "weakest_layer": str(reasoning_payload["weakest_layer"]),
                "weakest_ratio": float(reasoning_payload["weakest_ratio"]),
                "confidence": reasoning_payload["confidence"],
            },
            "recommendations": recommendations,
        }
        if isinstance(gateway_metrics, dict) and gateway_metrics:
            report["gateway"] = gateway_metrics

        history = previous_state.get("history", []) if isinstance(previous_state.get("history", []), list) else []
        history.append(report)
        bounded_history = history[-self._MAX_QUALITY_HISTORY :]
        baseline = baseline_payload if baseline_payload else report

        state = {
            "version": 1,
            "updated_at": str(report["sampled_at"]),
            "baseline": baseline,
            "current": report,
            "history": bounded_history,
            "tuning": self._merge_quality_tuning_state(previous_state.get("tuning", {}), tuning_patch),
        }
        self._atomic_write_text_locked(
            self.quality_state_path,
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return report

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
        cls._atomic_write_text(path, json.dumps(default_payload, ensure_ascii=False, indent=2) + "\n")

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
        MemoryStore._atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _normalize_user_id(user_id: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(user_id or "default").strip())
        return clean or "default"

    @staticmethod
    def _normalize_session_id(session_id: str) -> str:
        return str(session_id or "").strip()

    @classmethod
    def _parent_session_id(cls, session_id: str) -> str:
        clean = cls._normalize_session_id(session_id)
        if not clean:
            return ""
        marker = ":subagent"
        if clean.endswith(marker):
            return clean[: -len(marker)].rstrip(":")
        if marker in clean:
            head, _, _ = clean.rpartition(marker)
            return head.rstrip(":")
        return ""

    @classmethod
    def _working_memory_share_group(cls, session_id: str) -> str:
        clean = cls._normalize_session_id(session_id)
        if not clean:
            return ""
        parent = cls._parent_session_id(clean)
        return parent or clean

    @classmethod
    def _default_working_memory_share_scope(cls, session_id: str) -> str:
        return "parent" if cls._parent_session_id(session_id) else "family"

    @classmethod
    def _normalize_working_memory_share_scope(cls, value: Any, *, session_id: str) -> str:
        clean = str(value or "").strip().lower()
        if clean in cls._WORKING_MEMORY_SHARE_SCOPE_SET:
            return clean
        return cls._default_working_memory_share_scope(session_id)

    @classmethod
    def _normalize_working_memory_promotion_state(cls, value: Any) -> dict[str, Any]:
        payload = value if isinstance(value, dict) else {}
        try:
            message_count = int(payload.get("last_promoted_message_count", payload.get("lastPromotedMessageCount", 0)) or 0)
        except Exception:
            message_count = 0
        try:
            total = int(payload.get("total_promotions", payload.get("totalPromotions", 0)) or 0)
        except Exception:
            total = 0
        return {
            "last_promoted_signature": str(
                payload.get("last_promoted_signature", payload.get("lastPromotedSignature", "")) or ""
            ).strip(),
            "last_promoted_at": str(payload.get("last_promoted_at", payload.get("lastPromotedAt", "")) or "").strip(),
            "last_promoted_message_count": max(0, message_count),
            "total_promotions": max(0, total),
        }

    @classmethod
    def _default_working_memory_state(cls) -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": "",
            "sessions": {},
        }

    @classmethod
    def _normalize_working_memory_entry(
        cls,
        payload: Any,
        *,
        session_id: str,
        fallback_user_id: str = "default",
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        clean_session_id = cls._normalize_session_id(payload.get("session_id", session_id))
        if not clean_session_id:
            clean_session_id = cls._normalize_session_id(session_id)
        role = str(payload.get("role", "") or "").strip().lower() or "user"
        content = " ".join(str(payload.get("content", payload.get("text", "")) or "").split())
        if not content:
            return None
        created_at = str(payload.get("created_at", payload.get("createdAt", "")) or "").strip() or cls._utcnow_iso()
        parent_session_id = cls._normalize_session_id(payload.get("parent_session_id", payload.get("parentSessionId", "")))
        if not parent_session_id:
            parent_session_id = cls._parent_session_id(clean_session_id)
        share_group = cls._normalize_session_id(payload.get("share_group", payload.get("shareGroup", "")))
        if not share_group:
            share_group = parent_session_id or clean_session_id
        share_scope = cls._normalize_working_memory_share_scope(
            payload.get("share_scope", payload.get("shareScope", "")),
            session_id=clean_session_id,
        )
        metadata = cls._normalize_memory_metadata(payload.get("metadata", {}))
        return {
            "session_id": clean_session_id,
            "role": role,
            "content": content,
            "created_at": created_at,
            "user_id": cls._normalize_user_id(str(payload.get("user_id", payload.get("userId", fallback_user_id)) or fallback_user_id)),
            "share_group": share_group,
            "share_scope": share_scope,
            "parent_session_id": parent_session_id,
            "metadata": metadata,
        }

    @classmethod
    def _normalize_working_memory_session(
        cls,
        session_id: str,
        payload: Any,
    ) -> dict[str, Any] | None:
        clean_session_id = cls._normalize_session_id(session_id)
        if not clean_session_id:
            return None
        raw = payload if isinstance(payload, dict) else {}
        parent_session_id = cls._normalize_session_id(raw.get("parent_session_id", raw.get("parentSessionId", "")))
        if not parent_session_id:
            parent_session_id = cls._parent_session_id(clean_session_id)
        share_group = cls._normalize_session_id(raw.get("share_group", raw.get("shareGroup", "")))
        if not share_group:
            share_group = parent_session_id or clean_session_id
        share_scope = cls._normalize_working_memory_share_scope(
            raw.get("share_scope", raw.get("shareScope", "")),
            session_id=clean_session_id,
        )
        updated_at = str(raw.get("updated_at", raw.get("updatedAt", "")) or "").strip()
        user_id = cls._normalize_user_id(str(raw.get("user_id", raw.get("userId", "default")) or "default"))
        promotion = cls._normalize_working_memory_promotion_state(raw.get("promotion", {}))
        messages_raw = raw.get("messages", [])
        messages: list[dict[str, Any]] = []
        if isinstance(messages_raw, list):
            for item in messages_raw:
                normalized = cls._normalize_working_memory_entry(
                    item,
                    session_id=clean_session_id,
                    fallback_user_id=user_id,
                )
                if normalized is not None:
                    messages.append(normalized)
        if messages:
            messages = sorted(messages, key=lambda item: str(item.get("created_at", "") or ""))[
                -cls._WORKING_MEMORY_MAX_MESSAGES_PER_SESSION :
            ]
            if not updated_at:
                updated_at = str(messages[-1].get("created_at", "") or "")
            user_id = str(messages[-1].get("user_id", user_id) or user_id)
        return {
            "session_id": clean_session_id,
            "user_id": user_id,
            "share_group": share_group,
            "share_scope": share_scope,
            "parent_session_id": parent_session_id,
            "promotion": promotion,
            "updated_at": updated_at,
            "messages": messages,
        }

    @classmethod
    def _normalize_working_memory_state_payload(cls, payload: Any) -> dict[str, Any]:
        raw = payload if isinstance(payload, dict) else {}
        sessions_raw = raw.get("sessions", {})
        sessions: dict[str, dict[str, Any]] = {}
        if isinstance(sessions_raw, dict):
            for key, value in sessions_raw.items():
                normalized = cls._normalize_working_memory_session(str(key or ""), value)
                if normalized is not None:
                    sessions[normalized["session_id"]] = normalized
        if len(sessions) > cls._WORKING_MEMORY_MAX_SESSIONS:
            ordered = sorted(
                sessions.values(),
                key=lambda item: str(item.get("updated_at", "") or ""),
            )
            sessions = {item["session_id"]: item for item in ordered[-cls._WORKING_MEMORY_MAX_SESSIONS :]}
        updated_at = str(raw.get("updated_at", raw.get("updatedAt", "")) or "").strip()
        if not updated_at and sessions:
            updated_at = max(str(item.get("updated_at", "") or "") for item in sessions.values())
        return {
            "version": 1,
            "updated_at": updated_at,
            "sessions": sessions,
        }

    def _load_working_memory_state(self) -> dict[str, Any]:
        with self._locked_file(self.working_memory_path, "a+", exclusive=False) as fh:
            fh.seek(0)
            raw = fh.read()
        try:
            payload = json.loads(str(raw or "").strip() or "{}")
        except Exception:
            payload = {}
        return self._normalize_working_memory_state_payload(payload)

    def _save_working_memory_state(self, payload: dict[str, Any]) -> None:
        normalized = self._normalize_working_memory_state_payload(payload)
        self._atomic_write_text_locked(
            self.working_memory_path,
            json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def set_working_memory_share_scope(self, session_id: str, share_scope: str) -> dict[str, Any]:
        clean_session_id = self._normalize_session_id(session_id)
        if not clean_session_id:
            raise ValueError("session_id is required")
        resolved_scope = self._normalize_working_memory_share_scope(share_scope, session_id=clean_session_id)
        with self._locked_file(self.working_memory_path, "a+", exclusive=True) as fh:
            fh.seek(0)
            raw = fh.read()
            try:
                payload = json.loads(str(raw or "").strip() or "{}")
            except Exception:
                payload = {}
            state = self._normalize_working_memory_state_payload(payload)
            sessions = dict(state.get("sessions", {}))
            existing = self._normalize_working_memory_session(clean_session_id, sessions.get(clean_session_id, {}))
            if existing is None:
                existing = {
                    "session_id": clean_session_id,
                    "user_id": "default",
                    "share_group": self._working_memory_share_group(clean_session_id),
                    "share_scope": self._default_working_memory_share_scope(clean_session_id),
                    "parent_session_id": self._parent_session_id(clean_session_id),
                    "promotion": self._normalize_working_memory_promotion_state({}),
                    "updated_at": "",
                    "messages": [],
                }
            existing["share_scope"] = resolved_scope
            sessions[clean_session_id] = existing
            state["sessions"] = sessions
            state["updated_at"] = self._utcnow_iso()
            normalized_state = self._normalize_working_memory_state_payload(state)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(normalized_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            self._flush_and_fsync(fh)
        return {
            "session_id": clean_session_id,
            "share_scope": resolved_scope,
        }

    @classmethod
    def _working_memory_related_sessions(
        cls,
        sessions: dict[str, dict[str, Any]],
        primary: dict[str, Any],
        *,
        include_shared_subagents: bool,
    ) -> list[dict[str, Any]]:
        if not include_shared_subagents:
            return [primary]
        primary_session_id = str(primary.get("session_id", "") or "")
        share_group = str(primary.get("share_group", "") or "")
        parent_session_id = str(primary.get("parent_session_id", "") or "")
        share_scope = cls._normalize_working_memory_share_scope(primary.get("share_scope", ""), session_id=primary_session_id)
        related = [primary]
        if share_scope == "private" or not share_group:
            return related

        for other_session_id, payload in sessions.items():
            if str(other_session_id or "") == primary_session_id:
                continue
            normalized = cls._normalize_working_memory_session(str(other_session_id or ""), payload)
            if normalized is None:
                continue
            if str(normalized.get("share_group", "") or "") != share_group:
                continue
            other_id = str(normalized.get("session_id", "") or "")
            other_scope = cls._normalize_working_memory_share_scope(normalized.get("share_scope", ""), session_id=other_id)
            is_parent = bool(parent_session_id and other_id == parent_session_id)
            is_child = bool(primary_session_id and str(normalized.get("parent_session_id", "") or "") == primary_session_id)
            is_sibling = bool(parent_session_id and str(normalized.get("parent_session_id", "") or "") == parent_session_id)

            if is_parent:
                related.append(normalized)
                continue
            if is_child and share_scope == "family" and other_scope in {"parent", "family"}:
                related.append(normalized)
                continue
            if is_sibling and share_scope == "family" and other_scope == "family":
                related.append(normalized)
        return related

    @classmethod
    def _working_memory_recent_direct_messages(cls, entry: dict[str, Any]) -> list[dict[str, Any]]:
        messages_raw = entry.get("messages", [])
        if not isinstance(messages_raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in messages_raw:
            normalized = cls._normalize_working_memory_entry(
                item,
                session_id=str(entry.get("session_id", "") or ""),
                fallback_user_id=str(entry.get("user_id", "default") or "default"),
            )
            if normalized is None:
                continue
            out.append(normalized)
        return out

    @classmethod
    def _is_working_episode_record(cls, row: MemoryRecord) -> bool:
        metadata = cls._normalize_memory_metadata(getattr(row, "metadata", {}))
        if bool(metadata.get("working_memory_promoted", False)):
            return True
        return str(getattr(row, "source", "") or "").startswith("working-session:")

    @classmethod
    def _working_episode_context(cls, row: MemoryRecord) -> dict[str, str]:
        metadata = cls._normalize_memory_metadata(getattr(row, "metadata", {}))
        session_id = cls._normalize_session_id(
            metadata.get("working_memory_session_id", metadata.get("session_id", ""))
        )
        if not session_id and str(getattr(row, "source", "") or "").startswith("working-session:"):
            session_id = cls._normalize_session_id(str(getattr(row, "source", "") or "")[len("working-session:") :])
        parent_session_id = cls._normalize_session_id(
            metadata.get("working_memory_parent_session_id", metadata.get("parent_session_id", ""))
        )
        if not parent_session_id:
            parent_session_id = cls._parent_session_id(session_id)
        share_group = cls._normalize_session_id(
            metadata.get("working_memory_share_group", metadata.get("share_group", ""))
        )
        if not share_group:
            share_group = cls._working_memory_share_group(session_id)
        share_scope = cls._normalize_working_memory_share_scope(
            metadata.get("working_memory_share_scope", metadata.get("share_scope", "")),
            session_id=session_id,
        )
        return {
            "session_id": session_id,
            "parent_session_id": parent_session_id,
            "share_group": share_group,
            "share_scope": share_scope,
        }

    @classmethod
    def _working_episode_visible_in_session(cls, row: MemoryRecord, *, session_id: str) -> bool:
        clean_session_id = cls._normalize_session_id(session_id)
        if not cls._is_working_episode_record(row) or not clean_session_id:
            return True
        row_ctx = cls._working_episode_context(row)
        row_session_id = str(row_ctx.get("session_id", "") or "")
        row_parent_session_id = str(row_ctx.get("parent_session_id", "") or "")
        row_share_group = str(row_ctx.get("share_group", "") or "")
        row_share_scope = str(row_ctx.get("share_scope", "") or "")
        if not row_session_id:
            return True
        if row_session_id == clean_session_id:
            return True
        current_parent = cls._parent_session_id(clean_session_id)
        current_group = cls._working_memory_share_group(clean_session_id)
        if not row_share_group or row_share_group != current_group:
            return False
        if row_share_scope == "private":
            return False
        if clean_session_id == row_parent_session_id:
            return row_share_scope in {"parent", "family"}
        if current_parent and row_session_id == current_parent:
            return row_share_scope == "family"
        if row_parent_session_id == clean_session_id:
            return row_share_scope == "family"
        if current_parent and row_parent_session_id == current_parent:
            return row_share_scope == "family"
        return False

    @classmethod
    def _episodic_session_boost(cls, row: MemoryRecord, *, session_id: str) -> float:
        clean_session_id = cls._normalize_session_id(session_id)
        if not clean_session_id or not cls._is_working_episode_record(row):
            return 0.0
        row_ctx = cls._working_episode_context(row)
        row_session_id = str(row_ctx.get("session_id", "") or "")
        row_parent_session_id = str(row_ctx.get("parent_session_id", "") or "")
        row_share_scope = str(row_ctx.get("share_scope", "") or "")
        if row_session_id == clean_session_id:
            return 0.6
        if not cls._working_episode_visible_in_session(row, session_id=clean_session_id):
            return 0.0
        current_parent = cls._parent_session_id(clean_session_id)
        if clean_session_id == row_parent_session_id:
            return 0.38 if row_share_scope == "parent" else 0.46
        if row_parent_session_id == clean_session_id:
            return 0.34 if row_share_scope == "family" else 0.0
        if current_parent and row_parent_session_id == current_parent and row_share_scope == "family":
            return 0.28
        return 0.14

    @classmethod
    def _episodic_digest_label(cls, *, active_session_id: str, target_session_id: str) -> str:
        clean_active = cls._normalize_session_id(active_session_id)
        clean_target = cls._normalize_session_id(target_session_id)
        if not clean_target:
            return "unknown"
        if clean_target == clean_active:
            return "current"
        parent = cls._parent_session_id(clean_active)
        if clean_target == parent:
            return "parent"
        if cls._parent_session_id(clean_target) == clean_active:
            return "child"
        if parent and cls._parent_session_id(clean_target) == parent:
            return "sibling"
        return "related"

    def _synthesize_visible_episode_digest(
        self,
        *,
        query: str,
        session_id: str,
        records: list[MemoryRecord],
        curated_importance: dict[str, float],
        curated_mentions: dict[str, int],
        semantic_enabled: bool,
        limit: int,
    ) -> dict[str, Any] | None:
        clean_session_id = self._normalize_session_id(session_id)
        if not clean_session_id:
            return None
        episodic_records = [row for row in records if self._is_working_episode_record(row)]
        if not episodic_records:
            return None
        ranked = self._rank_records(
            query,
            episodic_records,
            curated_importance=curated_importance,
            curated_mentions=curated_mentions,
            limit=max(1, min(8, limit)),
            semantic_enabled=semantic_enabled,
            session_id=clean_session_id,
        )
        if not ranked:
            return None

        groups: list[dict[str, Any]] = []
        seen_sessions: set[str] = set()
        for row in ranked:
            ctx = self._working_episode_context(row)
            target_session_id = str(ctx.get("session_id", "") or "")
            if not target_session_id or target_session_id in seen_sessions:
                continue
            seen_sessions.add(target_session_id)
            groups.append(
                {
                    "session_id": target_session_id,
                    "label": self._episodic_digest_label(
                        active_session_id=clean_session_id,
                        target_session_id=target_session_id,
                    ),
                    "share_scope": str(ctx.get("share_scope", "") or ""),
                    "created_at": str(getattr(row, "created_at", "") or ""),
                    "source": str(getattr(row, "source", "") or ""),
                    "text": self._compact_whitespace(str(getattr(row, "text", "") or ""))[:220],
                    "memory_id": str(getattr(row, "id", "") or ""),
                }
            )
            if len(groups) >= max(1, min(4, limit)):
                break
        if not groups:
            return None

        summary_parts = [
            f"{item['label']}:{item['session_id']} -> {item['text']}"
            for item in groups
            if str(item.get("text", "") or "")
        ]
        return {
            "session_id": clean_session_id,
            "count": len(groups),
            "sessions": groups,
            "summary": " | ".join(summary_parts),
        }

    @classmethod
    def _working_memory_episode_summary(cls, session_id: str, messages: list[dict[str, Any]]) -> str:
        clean_session_id = cls._normalize_session_id(session_id) or "unknown"
        recent = messages[-cls._WORKING_MEMORY_PROMOTION_WINDOW :]
        user_rows = [str(item.get("content", "") or "") for item in recent if str(item.get("role", "") or "") == "user"]
        assistant_rows = [str(item.get("content", "") or "") for item in recent if str(item.get("role", "") or "") == "assistant"]
        topics: list[str] = []
        for item in recent:
            for topic in cls._extract_topics(str(item.get("content", "") or "")):
                if topic not in topics:
                    topics.append(topic)
        details = [
            f"Session episode for {clean_session_id} captured {len(recent)} recent messages."
        ]
        if topics:
            details.append(f"Topics: {', '.join(topics[:6])}.")
        if user_rows:
            details.append(f"Latest user intent: {cls._compact_whitespace(user_rows[-1])[:180]}.")
        if assistant_rows:
            details.append(f"Latest assistant outcome: {cls._compact_whitespace(assistant_rows[-1])[:180]}.")
        return " ".join(detail for detail in details if detail).strip()

    def _promote_working_memory_locked(
        self,
        *,
        sessions: dict[str, dict[str, Any]],
        session_id: str,
        force: bool,
    ) -> MemoryRecord | None:
        entry = self._normalize_working_memory_session(session_id, sessions.get(session_id, {}))
        if entry is None:
            self._diagnostics["working_memory_promotion_skips"] = int(self._diagnostics["working_memory_promotion_skips"]) + 1
            return None

        direct_messages = self._working_memory_recent_direct_messages(entry)
        if len(direct_messages) < self._WORKING_MEMORY_PROMOTION_MIN_MESSAGES and not force:
            self._diagnostics["working_memory_promotion_skips"] = int(self._diagnostics["working_memory_promotion_skips"]) + 1
            return None
        recent = direct_messages[-self._WORKING_MEMORY_PROMOTION_WINDOW :]

        candidate_messages = [
            {"role": str(item.get("role", "") or ""), "content": str(item.get("content", "") or "")}
            for item in recent
        ]
        if len(self._extract_consolidation_lines(candidate_messages)) < 2 and not force:
            self._diagnostics["working_memory_promotion_skips"] = int(self._diagnostics["working_memory_promotion_skips"]) + 1
            return None

        raw_resource_text = "\n".join(
            f"{str(item.get('role', '') or '').strip().lower()}: {self._compact_whitespace(str(item.get('content', '') or ''))}"
            for item in recent
            if self._compact_whitespace(str(item.get("content", "") or ""))
        ).strip()
        if not raw_resource_text:
            self._diagnostics["working_memory_promotion_skips"] = int(self._diagnostics["working_memory_promotion_skips"]) + 1
            return None

        promotion = self._normalize_working_memory_promotion_state(entry.get("promotion", {}))
        signature = self._chunk_signature(raw_resource_text.splitlines())
        message_count = len(direct_messages)
        if not force:
            if signature == str(promotion.get("last_promoted_signature", "") or ""):
                self._diagnostics["working_memory_promotion_skips"] = int(self._diagnostics["working_memory_promotion_skips"]) + 1
                return None
            last_count = int(promotion.get("last_promoted_message_count", 0) or 0)
            if last_count > 0 and (message_count - last_count) < self._WORKING_MEMORY_PROMOTION_STEP:
                self._diagnostics["working_memory_promotion_skips"] = int(self._diagnostics["working_memory_promotion_skips"]) + 1
                return None

        session_key = str(entry.get("session_id", session_id) or session_id)
        happened_at = str(recent[-1].get("created_at", "") or self._utcnow_iso())
        summary = self._working_memory_episode_summary(session_key, recent)
        metadata = self._normalize_memory_metadata(
            {
                "working_memory_promoted": True,
                "working_memory_session_id": session_key,
                "working_memory_parent_session_id": str(entry.get("parent_session_id", "") or ""),
                "working_memory_share_group": str(entry.get("share_group", "") or ""),
                "working_memory_share_scope": str(entry.get("share_scope", "") or ""),
                "working_memory_message_count": len(recent),
                "working_memory_signature": signature,
                "skip_profile_sync": True,
            }
        )
        record = self.add(
            summary,
            source=f"working-session:{session_key}",
            raw_resource_text=raw_resource_text,
            user_id=str(entry.get("user_id", "default") or "default"),
            shared=False,
            metadata=metadata,
            reasoning_layer="outcome",
            confidence=min(0.95, 0.55 + (0.05 * len(recent))),
            memory_type="event",
            happened_at=happened_at,
        )
        promotion["last_promoted_signature"] = signature
        promotion["last_promoted_at"] = self._utcnow_iso()
        promotion["last_promoted_message_count"] = message_count
        promotion["total_promotions"] = int(promotion.get("total_promotions", 0) or 0) + 1
        entry["promotion"] = promotion
        sessions[session_key] = entry
        self._diagnostics["working_memory_promotions"] = int(self._diagnostics["working_memory_promotions"]) + 1
        return record

    def promote_working_set(self, session_id: str, *, force: bool = False) -> dict[str, Any]:
        clean_session_id = self._normalize_session_id(session_id)
        if not clean_session_id:
            return {"status": "failed", "error": "session_id is required", "record": None}
        record: MemoryRecord | None = None
        with self._locked_file(self.working_memory_path, "a+", exclusive=True) as fh:
            fh.seek(0)
            raw = fh.read()
            try:
                payload = json.loads(str(raw or "").strip() or "{}")
            except Exception:
                payload = {}
            state = self._normalize_working_memory_state_payload(payload)
            sessions = dict(state.get("sessions", {}))
            record = self._promote_working_memory_locked(sessions=sessions, session_id=clean_session_id, force=force)
            state["sessions"] = sessions
            state["updated_at"] = self._utcnow_iso()
            normalized_state = self._normalize_working_memory_state_payload(state)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(normalized_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            self._flush_and_fsync(fh)
        if record is None:
            return {"status": "skipped", "record": None}
        return {"status": "ok", "record": asdict(record)}

    def remember_working_set(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
        allow_promotion: bool = True,
    ) -> None:
        clean_session_id = self._normalize_session_id(session_id)
        clean_content = " ".join(str(content or "").split())
        if not clean_session_id or not clean_content:
            return

        with self._locked_file(self.working_memory_path, "a+", exclusive=True) as fh:
            fh.seek(0)
            raw = fh.read()
            try:
                payload = json.loads(str(raw or "").strip() or "{}")
            except Exception:
                payload = {}
            state = self._normalize_working_memory_state_payload(payload)
            sessions = dict(state.get("sessions", {}))
            existing = self._normalize_working_memory_session(clean_session_id, sessions.get(clean_session_id, {}))
            if existing is None:
                existing = {
                    "session_id": clean_session_id,
                    "user_id": self._normalize_user_id(user_id),
                    "share_group": self._working_memory_share_group(clean_session_id),
                    "share_scope": self._default_working_memory_share_scope(clean_session_id),
                    "parent_session_id": self._parent_session_id(clean_session_id),
                    "promotion": self._normalize_working_memory_promotion_state({}),
                    "updated_at": "",
                    "messages": [],
                }

            entry = self._normalize_working_memory_entry(
                {
                    "session_id": clean_session_id,
                    "role": role,
                    "content": clean_content,
                    "user_id": self._normalize_user_id(user_id),
                    "share_group": existing["share_group"],
                    "share_scope": existing["share_scope"],
                    "parent_session_id": existing["parent_session_id"],
                    "metadata": self._normalize_memory_metadata(metadata),
                    "created_at": self._utcnow_iso(),
                },
                session_id=clean_session_id,
                fallback_user_id=user_id,
            )
            if entry is None:
                return

            messages = list(existing.get("messages", []))
            if messages:
                last = dict(messages[-1])
                if (
                    str(last.get("role", "") or "") == str(entry.get("role", "") or "")
                    and str(last.get("content", "") or "") == str(entry.get("content", "") or "")
                ):
                    merged_metadata = self._normalize_memory_metadata(
                        {
                            **self._normalize_memory_metadata(last.get("metadata", {})),
                            **self._normalize_memory_metadata(entry.get("metadata", {})),
                        }
                    )
                    last["metadata"] = merged_metadata
                    last["created_at"] = str(entry.get("created_at", "") or last.get("created_at", ""))
                    last["share_group"] = str(entry.get("share_group", "") or existing["share_group"])
                    last["share_scope"] = str(entry.get("share_scope", "") or existing["share_scope"])
                    last["parent_session_id"] = str(entry.get("parent_session_id", "") or existing["parent_session_id"])
                    last["user_id"] = str(entry.get("user_id", "") or existing["user_id"])
                    messages[-1] = last
                else:
                    messages.append(entry)
            else:
                messages.append(entry)

            messages = sorted(messages, key=lambda item: str(item.get("created_at", "") or ""))[
                -self._WORKING_MEMORY_MAX_MESSAGES_PER_SESSION :
            ]
            existing["messages"] = messages
            existing["updated_at"] = str(messages[-1].get("created_at", "") or self._utcnow_iso())
            existing["user_id"] = str(entry.get("user_id", "") or existing.get("user_id", "default"))
            sessions[clean_session_id] = existing
            if allow_promotion:
                promoted = self._promote_working_memory_locked(
                    sessions=sessions,
                    session_id=clean_session_id,
                    force=False,
                )
                if promoted is not None:
                    sessions[clean_session_id] = self._normalize_working_memory_session(
                        clean_session_id,
                        sessions.get(clean_session_id, {}),
                    ) or existing
            state["sessions"] = sessions
            state["updated_at"] = self._utcnow_iso()
            normalized_state = self._normalize_working_memory_state_payload(state)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(normalized_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            self._flush_and_fsync(fh)

    def get_working_set(
        self,
        session_id: str,
        *,
        limit: int = 8,
        include_shared_subagents: bool = True,
    ) -> list[dict[str, Any]]:
        clean_session_id = self._normalize_session_id(session_id)
        if not clean_session_id:
            return []

        bounded_limit = max(1, int(limit or 1))
        state = self._load_working_memory_state()
        sessions_raw = state.get("sessions", {})
        sessions = sessions_raw if isinstance(sessions_raw, dict) else {}
        primary = self._normalize_working_memory_session(clean_session_id, sessions.get(clean_session_id, {}))
        if primary is None:
            return []

        candidates = self._working_memory_related_sessions(
            sessions,
            primary,
            include_shared_subagents=include_shared_subagents,
        )

        entries: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for candidate in candidates:
            messages = candidate.get("messages", [])
            if not isinstance(messages, list):
                continue
            for item in messages:
                normalized = self._normalize_working_memory_entry(
                    item,
                    session_id=str(candidate.get("session_id", clean_session_id) or clean_session_id),
                    fallback_user_id=str(candidate.get("user_id", "default") or "default"),
                )
                if normalized is None:
                    continue
                key = (
                    str(normalized.get("session_id", "") or ""),
                    str(normalized.get("role", "") or ""),
                    str(normalized.get("content", "") or ""),
                    str(normalized.get("created_at", "") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                entries.append(normalized)

        entries.sort(key=lambda item: str(item.get("created_at", "") or ""), reverse=True)
        return entries[:bounded_limit]

    def _scope_paths(self, *, user_id: str = "default", shared: bool = False) -> dict[str, Path]:
        clean_user = self._normalize_user_id(user_id)
        if shared:
            root = self.shared_path
        elif clean_user == "default":
            root = self.memory_home
        else:
            root = self.users_path / clean_user
        return {
            "root": root,
            "history": self.history_path if root == self.memory_home else (root / "history.jsonl"),
            "curated": self.curated_path if (root == self.memory_home and self.curated_path is not None) else (root / "curated.json"),
            "checkpoints": self.checkpoints_path if root == self.memory_home else (root / "checkpoints.json"),
            "resources": self.resources_path if root == self.memory_home else (root / "resources"),
            "items": self.items_path if root == self.memory_home else (root / "items"),
            "categories": self.categories_path if root == self.memory_home else (root / "categories"),
        }

    def _ensure_scope_paths(self, scope: dict[str, Path]) -> None:
        root = scope["root"]
        root.mkdir(parents=True, exist_ok=True)
        scope["resources"].mkdir(parents=True, exist_ok=True)
        scope["items"].mkdir(parents=True, exist_ok=True)
        scope["categories"].mkdir(parents=True, exist_ok=True)
        self._ensure_file(scope["history"], default="")
        self._ensure_file(scope["checkpoints"], default="{}\n")
        self._ensure_file(scope["curated"], default='{"version": 2, "facts": []}\n')

    def _iter_existing_scopes(self) -> list[dict[str, Path]]:
        scopes: list[dict[str, Path]] = []
        seen_roots: set[Path] = set()

        def _append(scope: dict[str, Path]) -> None:
            root = Path(scope["root"])
            if root in seen_roots or not root.exists():
                return
            seen_roots.add(root)
            scopes.append(scope)

        _append(self._scope_paths(user_id="default", shared=False))
        if self.users_path.exists():
            for child in sorted(self.users_path.iterdir()):
                if not child.is_dir():
                    continue
                _append(self._scope_paths(user_id=child.name, shared=False))
        _append(self._scope_paths(shared=True))
        return scopes

    def _scope_resource_file_path_for_timestamp(self, scope: dict[str, Path], stamp: str) -> Path:
        parsed = self._parse_iso_timestamp(stamp)
        if parsed.year <= 1:
            parsed = datetime.now(timezone.utc)
        return scope["resources"] / f"conv_{parsed.strftime('%Y_%m_%d')}.jsonl"

    def _scope_item_file_path(self, scope: dict[str, Path], category: str) -> Path:
        return scope["items"] / f"{self._safe_category_slug(category)}.json"

    def _scope_category_file_path(self, scope: dict[str, Path], category: str) -> Path:
        return scope["categories"] / f"{self._safe_category_slug(category)}.md"

    def _load_shared_optin_map(self) -> dict[str, bool]:
        payload = self._load_json_dict(self.shared_optin_path, {})
        out: dict[str, bool] = {}
        for key, value in payload.items():
            out[self._normalize_user_id(str(key))] = bool(value)
        return out

    def set_shared_opt_in(self, user_id: str, enabled: bool) -> dict[str, Any]:
        clean_user = self._normalize_user_id(user_id)
        payload = self._load_shared_optin_map()
        payload[clean_user] = bool(enabled)
        self._write_json_dict(self.shared_optin_path, payload)
        return {"user_id": clean_user, "enabled": bool(enabled)}

    def shared_opt_in(self, user_id: str) -> bool:
        clean_user = self._normalize_user_id(user_id)
        return bool(self._load_shared_optin_map().get(clean_user, False))

    def _load_branches_metadata(self) -> dict[str, Any]:
        payload = self._load_json_dict(self.branches_meta_path, self._default_branches_metadata())
        current = str(payload.get("current", "main") or "main")
        branches_raw = payload.get("branches", {})
        branches = branches_raw if isinstance(branches_raw, dict) else {}
        if "main" not in branches or not isinstance(branches.get("main"), dict):
            now_iso = self._utcnow_iso()
            branches["main"] = {"head": "", "created_at": now_iso, "updated_at": now_iso}
        payload["current"] = current if current in branches else "main"
        payload["branches"] = branches
        return payload

    def _save_branches_metadata(self, payload: dict[str, Any]) -> None:
        self._write_json_dict(self.branches_meta_path, payload)

    def _sync_branch_head_file(self) -> None:
        meta = self._load_branches_metadata()
        current = str(meta.get("current", "main") or "main")
        self._atomic_write_text(self.branch_head_path, f"{current}\n")

    def _set_current_branch(self, name: str) -> None:
        meta = self._load_branches_metadata()
        branches = meta.get("branches", {})
        if not isinstance(branches, dict) or name not in branches:
            raise ValueError(f"unknown branch: {name}")
        meta["current"] = name
        self._save_branches_metadata(meta)
        self._atomic_write_text(self.branch_head_path, f"{name}\n")

    def _advance_branch_head(self, branch_name: str, version_id: str) -> None:
        meta = self._load_branches_metadata()
        branches = meta.get("branches", {})
        if not isinstance(branches, dict):
            branches = {}
        now_iso = self._utcnow_iso()
        entry = branches.get(branch_name, {})
        if not isinstance(entry, dict):
            entry = {}
        created_at = str(entry.get("created_at", now_iso) or now_iso)
        branches[branch_name] = {
            "head": str(version_id or ""),
            "created_at": created_at,
            "updated_at": now_iso,
        }
        meta["branches"] = branches
        if branch_name not in branches:
            meta["current"] = "main"
        self._save_branches_metadata(meta)
        self._sync_branch_head_file()

    def _current_branch_name(self) -> str:
        return str(self._load_branches_metadata().get("current", "main") or "main")

    def _current_branch_head(self) -> str:
        meta = self._load_branches_metadata()
        current = str(meta.get("current", "main") or "main")
        branches = meta.get("branches", {})
        if not isinstance(branches, dict):
            return ""
        row = branches.get(current, {})
        if not isinstance(row, dict):
            return ""
        return str(row.get("head", "") or "")

    def _privacy_settings(self) -> dict[str, Any]:
        payload = self._load_json_dict(self.privacy_path, self._default_privacy())
        merged = self._default_privacy()
        merged.update(payload)
        return merged

    def _append_privacy_audit_event(
        self,
        *,
        action: str,
        reason: str,
        source: str = "",
        category: str = "",
        record_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        settings = self._privacy_settings()
        if not bool(settings.get("audit_log", True)):
            self._diagnostics["privacy_audit_skipped"] = int(self._diagnostics["privacy_audit_skipped"]) + 1
            return
        payload: dict[str, Any] = {
            "timestamp": self._utcnow_iso(),
            "action": str(action or "unknown"),
            "reason": str(reason or ""),
        }
        if source:
            payload["source"] = str(source)
        if category:
            payload["category"] = str(category)
        if record_id:
            payload["id"] = str(record_id)
        if isinstance(metadata, dict) and metadata:
            payload["metadata"] = metadata
        try:
            with self._locked_file(self.privacy_audit_path, "a", exclusive=True) as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._flush_and_fsync(fh)
            self._diagnostics["privacy_audit_writes"] = int(self._diagnostics["privacy_audit_writes"]) + 1
        except Exception as exc:
            self._diagnostics["privacy_audit_errors"] = int(self._diagnostics["privacy_audit_errors"]) + 1
            self._diagnostics["last_error"] = str(exc)

    @staticmethod
    def _encrypted_prefix() -> str:
        return "enc:v2:"

    @staticmethod
    def _legacy_encrypted_prefix() -> str:
        return "enc:v1:"

    @staticmethod
    def _xor_with_keystream(data: bytes, *, key: bytes, nonce: bytes) -> bytes:
        output = bytearray(len(data))
        counter = 0
        cursor = 0
        while cursor < len(data):
            block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
            take = min(len(block), len(data) - cursor)
            for idx in range(take):
                output[cursor + idx] = data[cursor + idx] ^ block[idx]
            cursor += take
            counter += 1
        return bytes(output)

    def _load_or_create_privacy_key(self) -> bytes | None:
        cached = self._privacy_key
        if isinstance(cached, (bytes, bytearray)) and len(cached) == 32:
            return bytes(cached)

        try:
            if self.privacy_key_path.exists():
                raw = self.privacy_key_path.read_bytes()
                if len(raw) == 32:
                    self._privacy_key = raw
                    self._diagnostics["privacy_key_load_events"] = int(self._diagnostics["privacy_key_load_events"]) + 1
                    return raw
                stripped = raw.strip()
                try:
                    decoded = base64.urlsafe_b64decode(stripped)
                except Exception:
                    decoded = b""
                if len(decoded) == 32:
                    self._privacy_key = decoded
                    self._diagnostics["privacy_key_load_events"] = int(self._diagnostics["privacy_key_load_events"]) + 1
                    return decoded
        except Exception as exc:
            self._diagnostics["privacy_key_errors"] = int(self._diagnostics["privacy_key_errors"]) + 1
            self._diagnostics["last_error"] = str(exc)

        key = secrets.token_bytes(32)
        try:
            fd = os.open(str(self.privacy_key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(key)
                    fh.flush()
                    try:
                        os.fsync(fh.fileno())
                    except Exception:
                        pass
            finally:
                try:
                    os.chmod(self.privacy_key_path, 0o600)
                except Exception:
                    pass
            self._privacy_key = key
            self._diagnostics["privacy_key_create_events"] = int(self._diagnostics["privacy_key_create_events"]) + 1
            return key
        except Exception as exc:
            self._diagnostics["privacy_key_errors"] = int(self._diagnostics["privacy_key_errors"]) + 1
            self._diagnostics["last_error"] = str(exc)
            return None

    def _is_encrypted_category(self, category: str, *, settings: dict[str, Any] | None = None) -> bool:
        payload = settings if isinstance(settings, dict) else self._privacy_settings()
        raw_categories = payload.get("encrypted_categories", [])
        if not isinstance(raw_categories, list):
            return False
        categories = {str(item or "").strip().lower() for item in raw_categories if str(item or "").strip()}
        return str(category or "").strip().lower() in categories

    def _encrypt_text_for_category(self, text: str, category: str, *, settings: dict[str, Any] | None = None) -> str:
        clean = str(text or "")
        if not clean:
            return clean
        if not self._is_encrypted_category(category, settings=settings):
            return clean
        try:
            key = self._load_or_create_privacy_key()
            if key is None:
                return clean
            nonce = secrets.token_bytes(16)
            ciphertext = self._xor_with_keystream(clean.encode("utf-8"), key=key, nonce=nonce)
            tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
            encoded = base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")
            self._diagnostics["privacy_encrypt_events"] = int(self._diagnostics["privacy_encrypt_events"]) + 1
            return f"{self._encrypted_prefix()}{encoded}"
        except Exception as exc:
            self._diagnostics["privacy_encrypt_errors"] = int(self._diagnostics["privacy_encrypt_errors"]) + 1
            self._diagnostics["last_error"] = str(exc)
            return clean

    def _decrypt_text_for_category(self, text: str, category: str, *, settings: dict[str, Any] | None = None) -> str:
        clean = str(text or "")
        if not clean:
            return clean
        prefix_v2 = self._encrypted_prefix()
        prefix_v1 = self._legacy_encrypted_prefix()
        if not clean.startswith(prefix_v2) and not clean.startswith(prefix_v1):
            return clean
        # Decrypt whenever marker is present to preserve backward compatibility
        # when privacy.encrypted_categories changes over time.
        _ = category
        _ = settings
        try:
            if clean.startswith(prefix_v2):
                encoded = clean[len(prefix_v2) :]
                payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
                if len(payload) < 16 + 32:
                    raise ValueError("invalid_enc_v2_payload")
                nonce = payload[:16]
                ciphertext = payload[16:-32]
                tag = payload[-32:]
                key = self._load_or_create_privacy_key()
                if key is None:
                    return clean
                expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
                if not hmac.compare_digest(tag, expected_tag):
                    raise ValueError("invalid_enc_v2_tag")
                decoded = self._xor_with_keystream(ciphertext, key=key, nonce=nonce).decode("utf-8")
            else:
                encoded = clean[len(prefix_v1) :]
                decoded = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
            self._diagnostics["privacy_decrypt_events"] = int(self._diagnostics["privacy_decrypt_events"]) + 1
            return decoded
        except Exception as exc:
            self._diagnostics["privacy_decrypt_errors"] = int(self._diagnostics["privacy_decrypt_errors"]) + 1
            self._diagnostics["last_error"] = str(exc)
            return clean

    @contextmanager
    def _locked_file(self, path: Path, mode: str, *, exclusive: bool):
        fallback_lock = self._path_lock(path) if fcntl is None else None
        if fallback_lock is not None:
            fallback_lock.acquire()
        try:
            with path.open(mode, encoding="utf-8") as fh:
                if fcntl is not None:
                    lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                    fcntl.flock(fh.fileno(), lock_mode)
                try:
                    yield fh
                finally:
                    if fcntl is not None:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            if fallback_lock is not None:
                fallback_lock.release()

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
        memory_type = cls._normalize_memory_type(row.get("memory_type", row.get("memoryType", "knowledge")))
        confidence = cls._normalize_confidence(row.get("confidence", 1.0), default=1.0)
        decay_rate = cls._normalize_decay_rate(
            row.get("decay_rate", row.get("decayRate", cls._default_decay_rate(memory_type=memory_type)))
        )
        reasoning_layer = cls._normalize_reasoning_layer(row.get("reasoning_layer", row.get("reasoningLayer", "fact")))
        modality = str(row.get("modality", "text") or "text").strip().lower() or "text"
        happened_at = str(row.get("happened_at", row.get("happenedAt", "")) or "")
        metadata = cls._normalize_memory_metadata(row.get("metadata", {}))

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
            "confidence": confidence,
            "decay_rate": decay_rate,
            "reasoning_layer": reasoning_layer,
            "memory_type": memory_type,
            "modality": modality,
            "happened_at": happened_at,
            "metadata": metadata,
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
            self._flush_and_fsync(fh)
        try:
            self.backend.upsert_embedding(
                str(record_id or ""),
                list(embedding),
                str(created_at or ""),
                str(source or ""),
            )
        except Exception:
            pass

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
        try:
            backend_embeddings = self.backend.fetch_embeddings(limit=20000)
            if isinstance(backend_embeddings, dict):
                for row_id, vector in backend_embeddings.items():
                    clean_id = str(row_id or "").strip()
                    normalized = self._normalize_embedding(vector)
                    if not clean_id or normalized is None:
                        continue
                    out[clean_id] = normalized
        except Exception:
            pass
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
            self._flush_and_fsync(fh)
        try:
            self.backend.delete_embeddings(list(removed_ids))
        except Exception:
            pass
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
            "preferences, relationships, knowledge, context, decisions, skills, events, facts. "
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
            return self._normalize_category_label(content)
        except Exception:
            return None

    @classmethod
    def _normalize_category_label(cls, raw_label: str) -> str | None:
        normalized = re.sub(r"[^a-z_\s]", " ", str(raw_label or "").strip().lower())
        normalized = " ".join(normalized.split())
        if not normalized:
            return None
        if normalized in cls._MEMORY_CATEGORIES:
            return normalized

        synonym_map: dict[str, tuple[str, ...]] = {
            "preferences": ("preference", "likes", "dislikes", "style", "habit"),
            "relationships": ("relationship", "contact", "family", "friend", "coworker", "team"),
            "knowledge": ("know", "knowledge", "information", "reference", "learned", "learning"),
            "context": ("context", "note", "background"),
            "decisions": ("decision", "chosen", "resolved", "resolution", "plan"),
            "skills": ("skill", "ability", "capability", "how to", "expertise"),
            "events": ("event", "schedule", "deadline", "meeting", "travel", "trip", "birthday"),
            "facts": ("fact", "factual"),
        }
        for category, aliases in synonym_map.items():
            if normalized == category:
                return category
            if any(alias in normalized for alias in aliases):
                return category
        return None

    @classmethod
    def _extract_entities(cls, text: str) -> dict[str, list[str]]:
        raw = str(text or "")
        entities = {
            "urls": cls._ENTITY_URL_RE.findall(raw),
            "emails": cls._ENTITY_EMAIL_RE.findall(raw),
            "dates": cls._ENTITY_DATE_RE.findall(raw),
            "times": cls._ENTITY_TIME_RE.findall(raw),
        }
        out: dict[str, list[str]] = {}
        for key, values in entities.items():
            unique: list[str] = []
            for value in values:
                clean = str(value or "").strip()
                if clean and clean not in unique:
                    unique.append(clean)
            out[key] = unique
        return out

    @staticmethod
    def _normalize_entity_value(value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @classmethod
    def _entity_match_score(
        cls,
        query_entities: dict[str, list[str]],
        memory_entities: dict[str, list[str]],
    ) -> float:
        score = 0.0
        for entity_type, weight in cls._ENTITY_MATCH_WEIGHTS.items():
            query_values_raw = query_entities.get(entity_type, []) if isinstance(query_entities, dict) else []
            memory_values_raw = memory_entities.get(entity_type, []) if isinstance(memory_entities, dict) else []
            query_values = {
                cls._normalize_entity_value(item)
                for item in query_values_raw
                if cls._normalize_entity_value(item)
            }
            memory_values = {
                cls._normalize_entity_value(item)
                for item in memory_values_raw
                if cls._normalize_entity_value(item)
            }
            if not query_values or not memory_values:
                continue
            overlap = len(query_values.intersection(memory_values))
            if overlap <= 0:
                continue
            score += min(float(weight), float(weight) * float(overlap))
        return max(0.0, min(cls._ENTITY_MATCH_MAX_BOOST, round(score, 6)))

    def _heuristic_category(self, text: str, source: str) -> str:
        normalized = str(text or "").lower()
        source_norm = str(source or "").lower()
        entities = self._extract_entities(text)
        has_date_time = bool(entities["dates"] or entities["times"])
        has_knowledge_entities = bool(entities["urls"] or entities["emails"])
        if any(token in normalized for token in ("prefer", "preference", "always", "never", "gosto", "prefiro")):
            return "preferences"
        if any(token in normalized for token in ("decide", "decision", "we will", "vamos", "escolhemos", "resolved")):
            return "decisions"
        if any(token in normalized for token in ("can ", "how to", "skill", "know how", "sei ", "consigo")):
            return "skills"
        if any(token in normalized for token in ("name is", "works at", "friend", "wife", "husband", "team", "cliente", "parceiro")):
            return "relationships"
        if has_date_time or any(
            token in normalized
            for token in (
                "deadline",
                "meeting",
                "appointment",
                "schedule",
                "trip",
                "travel",
                "birthday",
                "tomorrow",
                "next week",
                "flight",
            )
        ):
            return "events"
        if has_knowledge_entities or any(
            token in normalized
            for token in (
                "learn",
                "learned",
                "know",
                "knowledge",
                "documentation",
                "docs",
                "guide",
                "tutorial",
                "reference",
            )
        ):
            return "knowledge"
        if source_norm.startswith("curated:") or "fact" in normalized or "timezone" in normalized:
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
    def _memory_content_hash(text: str, memory_type: str) -> str:
        normalized = " ".join(str(text or "").strip().lower().split())
        content = f"{memory_type}:{normalized}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _infer_memory_type(self, text: str, source: str, *, category: str = "") -> str:
        normalized = str(text or "").strip().lower()
        source_norm = str(source or "").strip().lower()
        category_norm = str(category or "").strip().lower()
        happened_at = self._infer_happened_at(text)

        if source_norm.startswith("tool:") or source_norm.startswith("process:") or " tool " in f" {normalized} ":
            return "tool"
        if category_norm in {"preferences", "relationships"}:
            return "profile"
        if category_norm == "skills":
            return "skill"
        if category_norm == "events":
            return "event"
        if any(token in normalized for token in ("prefer", "preference", "timezone", "language", "my name", "sou ", "i am ")):
            return "profile"
        if any(token in normalized for token in ("every ", "usually", "often", "habit", "always", "normalmente", "costumo")):
            return "behavior"
        if happened_at or any(
            token in normalized
            for token in ("meeting", "deadline", "trip", "travel", "launch", "release", "weekend", "tomorrow", "today", "yesterday")
        ):
            return "event"
        if any(token in normalized for token in ("how to", "workflow", "runbook", "guide", "tutorial", "playbook", "can use", "sei fazer")):
            return "skill"
        return "knowledge"

    @classmethod
    def _infer_happened_at(cls, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""

        exact_dt = re.search(r"\b(\d{4}-\d{2}-\d{2})[tT ](\d{1,2}:\d{2})(?::\d{2})?\b", raw)
        if exact_dt:
            date_part = exact_dt.group(1)
            time_part = exact_dt.group(2)
            return f"{date_part}T{time_part}:00+00:00"

        exact_date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
        if exact_date:
            return f"{exact_date.group(1)}T00:00:00+00:00"

        lowered = raw.lower()
        today = datetime.now(timezone.utc).date()
        if "tomorrow" in lowered:
            return datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()
        if "yesterday" in lowered:
            return datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()
        if "today" in lowered:
            return datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        return ""

    def _prepare_memory_metadata(
        self,
        *,
        text: str,
        source: str,
        metadata: dict[str, Any] | None,
        memory_type: str,
        happened_at: str,
    ) -> dict[str, Any]:
        prepared = self._normalize_memory_metadata(metadata)
        entities = self._extract_entities(text)
        non_empty_entities = {key: value for key, value in entities.items() if value}
        if non_empty_entities and "entities" not in prepared:
            prepared["entities"] = non_empty_entities
        if happened_at and "happened_at_hint" not in prepared:
            prepared["happened_at_hint"] = happened_at
        source_session = self._source_session_key(source)
        if source_session and "source_session" not in prepared:
            prepared["source_session"] = source_session
        prepared.setdefault("content_hash", self._memory_content_hash(text, memory_type))
        return prepared

    @classmethod
    def _record_temporal_anchor(cls, row: MemoryRecord) -> str:
        happened_at = str(getattr(row, "happened_at", "") or "").strip()
        if happened_at and cls._parse_iso_timestamp(happened_at).year > 1:
            return happened_at
        return str(row.created_at or "")

    @staticmethod
    def _metadata_hint(metadata: dict[str, Any] | None) -> str:
        if not isinstance(metadata, dict):
            return ""
        for key in ("transcript", "caption", "description", "summary"):
            value = str(metadata.get(key, "") or "").strip()
            if value:
                return value[:600]
        return ""

    @staticmethod
    def _compact_whitespace(value: str) -> str:
        return " ".join(str(value or "").split())

    @classmethod
    def _try_ocr_image_text(cls, target: Path) -> str:
        try:
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore
        except Exception:
            return ""
        try:
            with Image.open(target) as image:
                extracted = pytesseract.image_to_string(image)
        except Exception:
            return ""
        return cls._compact_whitespace(extracted)

    @classmethod
    def _try_transcribe_audio_text(cls, target: Path) -> str:
        try:
            import whisper  # type: ignore

            model = whisper.load_model("base")
            result = model.transcribe(str(target))
            if isinstance(result, dict):
                return cls._compact_whitespace(str(result.get("text", "") or ""))
        except Exception:
            pass
        try:
            from faster_whisper import WhisperModel  # type: ignore

            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(target))
            joined = " ".join(str(getattr(seg, "text", "") or "") for seg in segments)
            return cls._compact_whitespace(joined)
        except Exception:
            return ""

    @classmethod
    def _memory_text_from_file(
        cls,
        file_path: str,
        *,
        modality: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        target = Path(file_path).expanduser()
        suffix = target.suffix.lower()
        hint = cls._metadata_hint(metadata)
        if suffix in cls._TEXT_LIKE_SUFFIXES:
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                content = ""
            excerpt = cls._compact_whitespace(content)[:4000].strip()
            if excerpt:
                return excerpt

        image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
        audio_suffixes = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
        modality_clean = str(modality or "").strip().lower()

        if suffix in image_suffixes or modality_clean == "image":
            ocr_text = cls._try_ocr_image_text(target)
            if ocr_text:
                return ocr_text[:4000]

        if suffix in audio_suffixes or modality_clean == "audio":
            transcript = cls._try_transcribe_audio_text(target)
            if transcript:
                return transcript[:4000]

        synthetic = [f"Ingested {modality} file reference: {target.name} ({target})."]
        if modality_clean == "image":
            synthetic.append("OCR hook unavailable; stored as reference.")
        if modality_clean == "audio":
            synthetic.append("Transcription hook unavailable; stored as reference.")
        if hint:
            synthetic.append(f"Supplemental metadata: {hint}")
        return cls._compact_whitespace(" ".join(synthetic))[:4000]

    @classmethod
    def _memory_text_from_url(
        cls,
        url: str,
        *,
        modality: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        raw_url = str(url or "").strip()
        hint = cls._metadata_hint(metadata)
        if not raw_url:
            parts = [f"Ingested {modality} URL reference: {raw_url}."]
            if hint:
                parts.append(f"Supplemental metadata: {hint}")
            return cls._compact_whitespace(" ".join(parts))[:4000]

        try:
            request = urllib.request.Request(raw_url, headers={"User-Agent": "ClawLiteMemory/1.0"})
            with urllib.request.urlopen(request, timeout=6.0) as response:
                payload = response.read(200_000)
                headers = getattr(response, "headers", None)

            content_type = ""
            charset = "utf-8"
            if headers is not None:
                try:
                    content_type = str(headers.get_content_type() or "").strip().lower()
                except Exception:
                    content_type = ""
                try:
                    charset = str(headers.get_content_charset() or "utf-8").strip() or "utf-8"
                except Exception:
                    charset = "utf-8"
                if not content_type:
                    try:
                        content_type = str(headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
                    except Exception:
                        content_type = ""

            decoded = payload.decode(charset, errors="ignore")
            extracted = ""
            if "json" in content_type:
                try:
                    parsed = json.loads(decoded)
                    if isinstance(parsed, (dict, list)):
                        extracted = json.dumps(parsed, ensure_ascii=False)
                    else:
                        extracted = str(parsed)
                except Exception:
                    extracted = decoded
            elif "html" in content_type:
                without_scripts = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", decoded)
                without_styles = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", without_scripts)
                no_tags = re.sub(r"(?s)<[^>]+>", " ", without_styles)
                extracted = unescape(no_tags)
            elif content_type.startswith("text/") or not content_type:
                extracted = decoded

            compact = cls._compact_whitespace(extracted)[:4000]
            if compact:
                return compact
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        except Exception:
            pass

        parts = [f"Ingested {modality} URL reference: {raw_url}."]
        if hint:
            parts.append(f"Supplemental metadata: {hint}")
        return cls._compact_whitespace(" ".join(parts))[:4000]

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

    def _privacy_block_reason(self, text: str) -> str | None:
        privacy = self._privacy_settings()
        patterns = privacy.get("never_memorize_patterns", [])
        if not isinstance(patterns, list):
            patterns = []
        lowered = str(text or "").lower()
        for item in patterns:
            pattern = str(item or "").strip().lower()
            if pattern and pattern in lowered:
                return f"pattern:{pattern}"
        return None

    def _privacy_allows_memorize(self, text: str) -> bool:
        return self._privacy_block_reason(text) is None

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

    def _update_profile_upcoming_events(self, record: MemoryRecord) -> None:
        if self._normalize_memory_type(getattr(record, "memory_type", "knowledge")) != "event":
            return
        happened_at = self._parse_iso_timestamp(str(getattr(record, "happened_at", "") or ""))
        if happened_at.year <= 1:
            return
        if happened_at.tzinfo is None:
            happened_at = happened_at.replace(tzinfo=timezone.utc)
        if happened_at < datetime.now(timezone.utc) - timedelta(days=1):
            return

        profile = self._load_json_dict(self.profile_path, self._default_profile())
        upcoming_raw = profile.get("upcoming_events", [])
        upcoming_events = list(upcoming_raw) if isinstance(upcoming_raw, list) else []
        event_id = self._metadata_content_hash(getattr(record, "metadata", {})) or str(record.id or uuid.uuid4().hex)
        title = self._compact_whitespace(str(record.text or ""))[:160]
        if not title:
            return

        filtered: list[dict[str, Any]] = []
        for item in upcoming_events:
            if not isinstance(item, dict):
                continue
            existing_id = str(item.get("id", "") or "").strip()
            existing_stamp = self._parse_iso_timestamp(str(item.get("happened_at", "") or ""))
            if existing_stamp.year > 1 and existing_stamp.tzinfo is None:
                existing_stamp = existing_stamp.replace(tzinfo=timezone.utc)
            if existing_stamp.year > 1 and existing_stamp < datetime.now(timezone.utc) - timedelta(days=1):
                continue
            if existing_id == event_id:
                continue
            filtered.append(item)

        filtered.append(
            {
                "id": event_id,
                "memory_id": str(record.id or ""),
                "title": title,
                "happened_at": happened_at.isoformat(),
                "source": str(record.source or ""),
                "category": str(record.category or "events"),
            }
        )
        filtered.sort(key=lambda item: str(item.get("happened_at", "") or ""))
        filtered = filtered[:12]

        if filtered != upcoming_events:
            profile["upcoming_events"] = filtered
            profile["updated_at"] = self._utcnow_iso()
            if not str(profile.get("learned_at", "")).strip():
                profile["learned_at"] = self._utcnow_iso()
            self._write_json_dict(self.profile_path, profile)

    def _update_profile_from_record(self, record: MemoryRecord) -> None:
        metadata = self._normalize_memory_metadata(getattr(record, "metadata", {}))
        skip_profile_sync = bool(metadata.get("skip_profile_sync", False))
        if not skip_profile_sync:
            self._update_profile_from_text(str(getattr(record, "text", "") or ""))
        self._update_profile_upcoming_events(record)

    def _curated_rank(self, row: dict[str, object]) -> tuple[float, int, int, datetime, datetime, str, str]:
        importance = float(row.get("importance", 0.0))
        mentions = int(row.get("mentions", 0))
        session_count = int(row.get("session_count", 0))
        last_seen = self._parse_iso_timestamp(str(row.get("last_seen_at", "")))
        created = self._parse_iso_timestamp(str(row.get("created_at", "")))
        row_decay = self._normalize_decay_rate(row.get("decay_rate", row.get("decayRate", 0.0)), default=0.0)
        memory_type = self._normalize_memory_type(row.get("memory_type", row.get("memoryType", "knowledge")))
        happened_at = str(row.get("happened_at", row.get("happenedAt", "")) or "")
        text = str(row.get("text", ""))
        rid = str(row.get("id", ""))
        temp_row = MemoryRecord(
            id=rid,
            text=text,
            source=str(row.get("source", "curated") or "curated"),
            created_at=str(row.get("created_at", "") or ""),
            category=str(row.get("category", "context") or "context"),
            updated_at=str(row.get("last_seen_at", "") or ""),
            confidence=self._normalize_confidence(row.get("confidence", 1.0), default=1.0),
            decay_rate=row_decay,
            memory_type=memory_type,
            happened_at=happened_at,
            metadata=self._normalize_memory_metadata(row.get("metadata", {})),
        )
        adjusted_importance = importance + self._upcoming_event_boost(temp_row) - self._decay_penalty(temp_row)
        return (adjusted_importance, mentions, session_count, last_seen, created, text, rid)

    def _prune_history(self) -> None:
        with self._locked_file(self.history_path, "r+", exclusive=True) as fh:
            lines = fh.read().splitlines()
            if len(lines) <= self._MAX_HISTORY_RECORDS:
                return
            kept = lines[-self._MAX_HISTORY_RECORDS :]
            fh.seek(0)
            fh.truncate()
            fh.write("\n".join(kept) + "\n")
            self._flush_and_fsync(fh)

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
            category = str(normalized.get("category", "context") or "context")
            normalized["text"] = self._decrypt_text_for_category(str(normalized.get("text", "") or ""), category)
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
                category = str(clean.get("category", "context") or "context")
                clean["text"] = self._encrypt_text_for_category(str(clean.get("text", "") or ""), category)
                normalized.append(clean)

        normalized.sort(key=self._curated_rank, reverse=True)
        payload = {"version": 2, "facts": normalized[: self._MAX_CURATED_FACTS]}
        encoded = json.dumps(payload, ensure_ascii=False, indent=2)
        self._atomic_write_text_locked(self.curated_path, encoded + "\n")

    def _read_curated_facts_from(self, curated_path: Path) -> list[dict[str, object]]:
        with self._locked_file(curated_path, "r", exclusive=False) as fh:
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
            category = str(normalized.get("category", "context") or "context")
            normalized["text"] = self._decrypt_text_for_category(str(normalized.get("text", "") or ""), category)
            out.append(normalized)
        return out

    def _write_curated_facts_to(self, curated_path: Path, facts: list[dict[str, object]]) -> None:
        normalized: list[dict[str, object]] = []
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            clean = self._normalize_curated_fact(fact)
            if clean is not None:
                category = str(clean.get("category", "context") or "context")
                clean["text"] = self._encrypt_text_for_category(str(clean.get("text", "") or ""), category)
                normalized.append(clean)

        normalized.sort(key=self._curated_rank, reverse=True)
        payload = {"version": 2, "facts": normalized[: self._MAX_CURATED_FACTS]}
        encoded = json.dumps(payload, ensure_ascii=False, indent=2)
        self._atomic_write_text_locked(curated_path, encoded + "\n")

    def _read_history_records_from(self, history_path: Path) -> list[MemoryRecord]:
        out: list[MemoryRecord] = []
        with self._locked_file(history_path, "r", exclusive=False) as fh:
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
            row = self._record_from_payload(payload)
            if row is None:
                continue
            row.text = self._decrypt_text_for_category(str(row.text or ""), row.category)
            out.append(row)
        return out

    @staticmethod
    def _source_session_key(source: str) -> str:
        return str(source or "").strip().lower() or "unknown"

    @classmethod
    def _candidate_importance(
        cls,
        *,
        role: str,
        text: str,
        repeated_count: int,
        memory_type: str = "knowledge",
        happened_at: str = "",
    ) -> float:
        score = 1.0
        if role == "user":
            score += 0.5
        if CURATION_HINT_RE.search(text):
            score += 1.0
        score += min(0.8, len(text) / 320.0)
        score += min(2.0, max(0, repeated_count - 1) * 0.35)
        normalized_type = cls._normalize_memory_type(memory_type)
        if normalized_type == "profile":
            score += 0.8
        elif normalized_type == "behavior":
            score += 0.45
        elif normalized_type in {"skill", "tool"}:
            score += 0.25
        elif normalized_type == "event":
            score += 0.15
            stamp = cls._parse_iso_timestamp(str(happened_at or ""))
            if stamp.year > 1:
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                delta_days = float((stamp - datetime.now(timezone.utc)).total_seconds()) / 86400.0
                if -1.0 <= delta_days <= 45.0:
                    score += 0.45
        return score

    def _curate_candidates(
        self,
        candidates: list[tuple[str, str]],
        *,
        source: str,
        repeated_count: int = 1,
        metadata: dict[str, Any] | None = None,
        reasoning_layer: str | None = None,
        confidence: float | None = None,
        memory_type: str | None = None,
        happened_at: str | None = None,
        decay_rate: float | None = None,
    ) -> None:
        if self.curated_path is None or not candidates:
            return
        current = self._read_curated_facts()
        by_norm = {self._normalize_memory_text(str(item["text"])): item for item in current}
        now_iso = datetime.now(timezone.utc).isoformat()
        source_session = self._source_session_key(source)
        resolved_reasoning_layer = self._normalize_reasoning_layer(reasoning_layer)
        resolved_confidence = self._normalize_confidence(confidence, default=1.0)
        changed = False
        for role, candidate in candidates:
            norm = self._normalize_memory_text(candidate)
            if not norm:
                continue
            inferred_memory_type = self._normalize_memory_type(memory_type or self._infer_memory_type(candidate, source))
            inferred_happened_at = str(happened_at or self._infer_happened_at(candidate) or "")
            inferred_decay_rate = self._normalize_decay_rate(
                decay_rate,
                default=self._default_decay_rate(
                    memory_type=inferred_memory_type,
                    category=self._categorize_memory(candidate, source),
                    happened_at=inferred_happened_at,
                ),
            )
            inferred_metadata = self._prepare_memory_metadata(
                text=candidate,
                source=source,
                metadata=metadata,
                memory_type=inferred_memory_type,
                happened_at=inferred_happened_at,
            )
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
                    "importance": self._candidate_importance(
                        role=role,
                        text=candidate,
                        repeated_count=repeated_count,
                        memory_type=inferred_memory_type,
                        happened_at=inferred_happened_at,
                    ),
                    "reasoning_layer": resolved_reasoning_layer,
                    "confidence": resolved_confidence,
                    "decay_rate": inferred_decay_rate,
                    "memory_type": inferred_memory_type,
                    "happened_at": inferred_happened_at,
                    "metadata": inferred_metadata,
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
                memory_type=inferred_memory_type,
                happened_at=inferred_happened_at,
            ) * 0.35
            existing["reasoning_layer"] = resolved_reasoning_layer
            existing["confidence"] = resolved_confidence
            existing["decay_rate"] = self._normalize_decay_rate(
                min(
                    self._normalize_decay_rate(existing.get("decay_rate", existing.get("decayRate", inferred_decay_rate)), default=inferred_decay_rate),
                    inferred_decay_rate,
                )
                * 0.9,
                default=inferred_decay_rate,
            )
            existing["memory_type"] = inferred_memory_type
            existing["happened_at"] = inferred_happened_at
            existing["metadata"] = self._normalize_memory_metadata(
                {
                    **self._normalize_memory_metadata(existing.get("metadata", {})),
                    **inferred_metadata,
                }
            )
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

    @staticmethod
    def _safe_category_slug(category: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(category or "context").strip().lower()).strip("_")
        return clean or "context"

    def _resource_file_path_for_timestamp(self, stamp: str) -> Path:
        parsed = self._parse_iso_timestamp(stamp)
        if parsed.year <= 1:
            parsed = datetime.now(timezone.utc)
        date_part = parsed.strftime("%Y_%m_%d")
        return self.resources_path / f"conv_{date_part}.jsonl"

    def _item_file_path(self, category: str) -> Path:
        return self.items_path / f"{self._safe_category_slug(category)}.json"

    def _category_file_path(self, category: str) -> Path:
        return self.categories_path / f"{self._safe_category_slug(category)}.md"

    def _append_resource_layer(self, *, record: MemoryRecord, raw_text: str) -> None:
        category = str(record.category or "context")
        payload = {
            "id": str(record.id or ""),
            "text": self._encrypt_text_for_category(str(raw_text or "").strip(), category),
            "source": str(record.source or ""),
            "category": category,
            "created_at": str(record.created_at or ""),
            "layer": MemoryLayer.RESOURCE.value,
            "reasoning_layer": self._normalize_reasoning_layer(record.reasoning_layer),
            "confidence": self._normalize_confidence(record.confidence, default=1.0),
        }
        if not payload["id"] or not payload["text"]:
            return
        resource_file = self._resource_file_path_for_timestamp(payload["created_at"])
        self._ensure_file(resource_file, default="")
        with self._locked_file(resource_file, "a", exclusive=True) as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._flush_and_fsync(fh)
        try:
            self.backend.upsert_layer_record(
                layer=MemoryLayer.RESOURCE.value,
                record_id=payload["id"],
                payload=payload,
                category=payload["category"],
                created_at=payload["created_at"],
                updated_at=payload["created_at"],
            )
        except Exception:
            pass

    def _load_category_items(self, category: str) -> list[dict[str, Any]]:
        item_path = self._item_file_path(category)
        if not item_path.exists():
            return []
        try:
            payload = json.loads(item_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict) and str(row.get("id", "")).strip():
                decoded = dict(row)
                decoded["text"] = self._decrypt_text_for_category(str(decoded.get("text", "") or ""), category)
                out.append(decoded)
        return out

    def _write_category_items(self, category: str, rows: list[dict[str, Any]]) -> None:
        item_path = self._item_file_path(category)
        item_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "category": str(category or "context"),
            "updated_at": self._utcnow_iso(),
            "items": rows,
        }
        self._atomic_write_text_locked(item_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def _update_category_summary_file(self, category: str) -> None:
        rows = self._load_category_items(category)
        category_path = self._category_file_path(category)
        category_path.parent.mkdir(parents=True, exist_ok=True)
        now_iso = self._utcnow_iso()
        sources: Counter[str] = Counter()
        for row in rows:
            sources[str(row.get("source", "unknown") or "unknown")] += 1
        top_sources = [
            f"- {source}: {count}"
            for source, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]
        recent_lines = [
            f"- {str(row.get('id', '') or '')}: {str(row.get('text', '') or '').strip()[:160]}"
            for row in rows[-5:]
        ]
        body = [
            f"# Category: {category}",
            "",
            f"Updated: {now_iso}",
            f"Total items: {len(rows)}",
            "",
            "## Top Sources",
            *(top_sources or ["- none"]),
            "",
            "## Recent Items",
            *(recent_lines or ["- none"]),
            "",
        ]
        self._atomic_write_text_locked(category_path, "\n".join(body))

    def _stored_history_payload(self, record: MemoryRecord) -> dict[str, Any]:
        payload = asdict(record)
        payload["text"] = self._encrypt_text_for_category(str(record.text or ""), record.category)
        return payload

    def _reinforce_record(
        self,
        existing: MemoryRecord,
        incoming: MemoryRecord,
        *,
        source: str,
        scope_key: str,
        reinforced_at: str,
    ) -> MemoryRecord:
        incoming_text = str(incoming.text or "").strip()
        existing_text = str(existing.text or "").strip()
        if len(incoming_text) > len(existing_text):
            text = incoming_text
        else:
            text = existing_text or incoming_text

        metadata = self._merge_reinforced_metadata(
            existing.metadata,
            incoming.metadata,
            source=source,
            scope_key=scope_key,
            reinforced_at=reinforced_at,
        )
        existing_decay = self._normalize_decay_rate(getattr(existing, "decay_rate", 0.0), default=0.0)
        incoming_decay = self._normalize_decay_rate(getattr(incoming, "decay_rate", 0.0), default=existing_decay or 0.0)
        if existing_decay > 0.0 and incoming_decay > 0.0:
            reinforced_decay = self._normalize_decay_rate(min(existing_decay, incoming_decay) * 0.9, default=min(existing_decay, incoming_decay))
        else:
            reinforced_decay = self._normalize_decay_rate(existing_decay or incoming_decay, default=0.0)
        return MemoryRecord(
            id=str(existing.id or incoming.id or uuid.uuid4().hex),
            text=text,
            source=str(existing.source or incoming.source or "user"),
            created_at=str(existing.created_at or incoming.created_at or reinforced_at),
            category=str(existing.category or incoming.category or "context"),
            user_id=str(existing.user_id or incoming.user_id or "default"),
            layer=self._normalize_layer(getattr(existing, "layer", MemoryLayer.ITEM.value)),
            reasoning_layer=self._normalize_reasoning_layer(getattr(incoming, "reasoning_layer", existing.reasoning_layer)),
            modality=str(incoming.modality or existing.modality or "text"),
            updated_at=str(reinforced_at or incoming.updated_at or existing.updated_at or ""),
            confidence=max(
                self._normalize_confidence(getattr(existing, "confidence", 1.0), default=1.0),
                self._normalize_confidence(getattr(incoming, "confidence", 1.0), default=1.0),
            ),
            decay_rate=reinforced_decay,
            emotional_tone=str(existing.emotional_tone or incoming.emotional_tone or "neutral"),
            memory_type=self._normalize_memory_type(getattr(existing, "memory_type", incoming.memory_type)),
            happened_at=str(existing.happened_at or incoming.happened_at or ""),
            metadata=metadata,
        )

    def _append_or_reinforce_history_record(
        self,
        history_path: Path,
        record: MemoryRecord,
        *,
        content_hash: str,
        scope_key: str,
        source: str,
        reinforced_at: str,
    ) -> tuple[MemoryRecord, bool]:
        self._ensure_file(history_path, default="")
        with self._locked_file(history_path, "r+", exclusive=True) as fh:
            lines = fh.read().splitlines()
            rewritten_lines: list[str] = []
            reinforced_row: MemoryRecord | None = None

            for line in lines:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    rewritten_lines.append(raw)
                    continue
                if not isinstance(payload, dict):
                    rewritten_lines.append(raw)
                    continue
                candidate = self._record_from_payload(payload)
                if candidate is None:
                    rewritten_lines.append(raw)
                    continue
                candidate.text = self._decrypt_text_for_category(str(candidate.text or ""), candidate.category)
                candidate_hash = self._record_content_hash(candidate)
                if (
                    reinforced_row is None
                    and candidate_hash == content_hash
                    and self._record_scope_key(candidate) == scope_key
                ):
                    reinforced_row = self._reinforce_record(
                        candidate,
                        record,
                        source=source,
                        scope_key=scope_key,
                        reinforced_at=reinforced_at,
                    )
                    rewritten_lines.append(json.dumps(self._stored_history_payload(reinforced_row), ensure_ascii=False))
                    continue
                rewritten_lines.append(raw)

            if reinforced_row is None:
                fh.seek(0, os.SEEK_END)
                fh.write(json.dumps(self._stored_history_payload(record), ensure_ascii=False) + "\n")
                self._flush_and_fsync(fh)
                return record, True

            fh.seek(0)
            fh.truncate()
            if rewritten_lines:
                fh.write("\n".join(rewritten_lines) + "\n")
            self._flush_and_fsync(fh)
            return reinforced_row, False

    def _upsert_history_record_by_id(self, history_path: Path, record: MemoryRecord, *, append_if_missing: bool = False) -> bool:
        self._ensure_file(history_path, default="")
        stored_payload = self._stored_history_payload(record)
        with self._locked_file(history_path, "r+", exclusive=True) as fh:
            lines = fh.read().splitlines()
            rewritten_lines: list[str] = []
            found = False

            for line in lines:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    rewritten_lines.append(raw)
                    continue
                if not isinstance(payload, dict):
                    rewritten_lines.append(raw)
                    continue
                if str(payload.get("id", "")).strip() == record.id:
                    rewritten_lines.append(json.dumps(stored_payload, ensure_ascii=False))
                    found = True
                    continue
                rewritten_lines.append(raw)

            if not found and append_if_missing:
                fh.seek(0, os.SEEK_END)
                fh.write(json.dumps(stored_payload, ensure_ascii=False) + "\n")
                self._flush_and_fsync(fh)
                return True

            if not found:
                return False

            fh.seek(0)
            fh.truncate()
            if rewritten_lines:
                fh.write("\n".join(rewritten_lines) + "\n")
            self._flush_and_fsync(fh)
            return True

    def _upsert_item_layer(self, record: MemoryRecord) -> None:
        category = str(record.category or "context")
        rows = self._load_category_items(category)
        row_payload = self._serialize_hit(record)
        stored_payload = dict(row_payload)
        stored_payload["text"] = self._encrypt_text_for_category(str(row_payload.get("text", "") or ""), category)
        updated_rows: list[dict[str, Any]] = []
        found = False
        for row in rows:
            if str(row.get("id", "")).strip() == record.id:
                updated_rows.append(stored_payload)
                found = True
            else:
                preserved = dict(row)
                preserved["text"] = self._encrypt_text_for_category(str(preserved.get("text", "") or ""), category)
                updated_rows.append(preserved)
        if not found:
            updated_rows.append(stored_payload)
        self._write_category_items(category, updated_rows)
        self._update_category_summary_file(category)
        category_path = self._category_file_path(category)
        now_iso = self._utcnow_iso()
        try:
            self.backend.upsert_layer_record(
                layer=MemoryLayer.ITEM.value,
                record_id=str(record.id),
                payload=stored_payload,
                category=category,
                created_at=str(record.created_at or ""),
                updated_at=str(record.updated_at or record.created_at or ""),
            )
            self.backend.upsert_layer_record(
                layer=MemoryLayer.CATEGORY.value,
                record_id=str(record.id),
                payload={
                    "category": category,
                    "path": str(category_path),
                    "updated_at": now_iso,
                    "total_items": len(updated_rows),
                },
                category=category,
                created_at=str(record.created_at or now_iso),
                updated_at=now_iso,
            )
        except Exception:
            pass

    def _persist_layer_artifacts(self, record: MemoryRecord, *, raw_resource_text: str) -> None:
        self._append_resource_layer(record=record, raw_text=raw_resource_text)
        self._upsert_item_layer(record)

    def _load_scope_category_items(self, scope: dict[str, Path], category: str) -> list[dict[str, Any]]:
        item_path = self._scope_item_file_path(scope, category)
        if not item_path.exists():
            return []
        try:
            payload = json.loads(item_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict) and str(row.get("id", "")).strip():
                decoded = dict(row)
                decoded["text"] = self._decrypt_text_for_category(str(decoded.get("text", "") or ""), category)
                out.append(decoded)
        return out

    def _write_scope_category_items(self, scope: dict[str, Path], category: str, rows: list[dict[str, Any]]) -> None:
        item_path = self._scope_item_file_path(scope, category)
        item_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "category": str(category or "context"),
            "updated_at": self._utcnow_iso(),
            "items": rows,
        }
        self._atomic_write_text_locked(item_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def _update_scope_category_summary_file(self, scope: dict[str, Path], category: str) -> None:
        rows = self._load_scope_category_items(scope, category)
        category_path = self._scope_category_file_path(scope, category)
        category_path.parent.mkdir(parents=True, exist_ok=True)
        now_iso = self._utcnow_iso()
        sources: Counter[str] = Counter()
        for row in rows:
            sources[str(row.get("source", "unknown") or "unknown")] += 1
        top_sources = [
            f"- {source}: {count}"
            for source, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]
        recent_lines = [
            f"- {str(row.get('id', '') or '')}: {str(row.get('text', '') or '').strip()[:160]}"
            for row in rows[-5:]
        ]
        body = [
            f"# Category: {category}",
            "",
            f"Updated: {now_iso}",
            f"Total items: {len(rows)}",
            "",
            "## Top Sources",
            *(top_sources or ["- none"]),
            "",
            "## Recent Items",
            *(recent_lines or ["- none"]),
            "",
        ]
        self._atomic_write_text_locked(category_path, "\n".join(body))

    def _upsert_item_layer_in_scope(self, scope: dict[str, Path], record: MemoryRecord) -> None:
        category = str(record.category or "context")
        rows = self._load_scope_category_items(scope, category)
        row_payload = self._serialize_hit(record)
        stored_payload = dict(row_payload)
        stored_payload["text"] = self._encrypt_text_for_category(str(row_payload.get("text", "") or ""), category)
        updated_rows: list[dict[str, Any]] = []
        found = False
        for row in rows:
            if str(row.get("id", "")).strip() == record.id:
                updated_rows.append(stored_payload)
                found = True
            else:
                preserved = dict(row)
                preserved["text"] = self._encrypt_text_for_category(str(preserved.get("text", "") or ""), category)
                updated_rows.append(preserved)
        if not found:
            updated_rows.append(stored_payload)
        self._write_scope_category_items(scope, category, updated_rows)
        self._update_scope_category_summary_file(scope, category)

    def _persist_layer_artifacts_to_scope(self, scope: dict[str, Path], record: MemoryRecord, *, raw_resource_text: str) -> None:
        category = str(record.category or "context")
        resource_payload = {
            "id": str(record.id or ""),
            "text": self._encrypt_text_for_category(str(raw_resource_text or "").strip(), category),
            "source": str(record.source or ""),
            "category": category,
            "created_at": str(record.created_at or ""),
            "layer": MemoryLayer.RESOURCE.value,
            "reasoning_layer": self._normalize_reasoning_layer(record.reasoning_layer),
            "confidence": self._normalize_confidence(record.confidence, default=1.0),
        }
        resource_file = self._scope_resource_file_path_for_timestamp(scope, resource_payload["created_at"])
        self._ensure_file(resource_file, default="")
        with self._locked_file(resource_file, "a", exclusive=True) as fh:
            fh.write(json.dumps(resource_payload, ensure_ascii=False) + "\n")
            self._flush_and_fsync(fh)
        self._upsert_item_layer_in_scope(scope, record)

    def _prune_item_and_category_layers(self, record_ids: set[str]) -> int:
        if not record_ids:
            return 0
        deleted = 0
        for item_file in self.items_path.glob("*.json"):
            try:
                payload = json.loads(item_file.read_text(encoding="utf-8") or "{}")
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            category = str(payload.get("category", item_file.stem) or item_file.stem)
            rows = payload.get("items", [])
            if not isinstance(rows, list):
                continue
            kept: list[dict[str, Any]] = []
            removed_here = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_id = str(row.get("id", "")).strip()
                if row_id and row_id in record_ids:
                    removed_here += 1
                    continue
                kept.append(row)
            if removed_here > 0:
                deleted += removed_here
                self._write_category_items(category, kept)
                self._update_category_summary_file(category)
        return deleted

    def _prune_resource_layer_for_ids(self, record_ids: set[str]) -> int:
        if not record_ids:
            return 0
        deleted = 0
        for resource_file in self.resources_path.glob("conv_*.jsonl"):
            try:
                with self._locked_file(resource_file, "r+", exclusive=True) as fh:
                    lines = fh.read().splitlines()
                    kept_lines: list[str] = []
                    for line in lines:
                        raw = line.strip()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            kept_lines.append(raw)
                            continue
                        if not isinstance(payload, dict):
                            kept_lines.append(raw)
                            continue
                        row_id = str(payload.get("id", "")).strip()
                        if row_id and row_id in record_ids:
                            deleted += 1
                            continue
                        kept_lines.append(raw)
                    fh.seek(0)
                    fh.truncate()
                    if kept_lines:
                        fh.write("\n".join(kept_lines) + "\n")
                    self._flush_and_fsync(fh)
            except Exception:
                continue
        return deleted

    def _prune_history_records_for_ids(self, history_path: Path, record_ids: set[str]) -> int:
        if not record_ids or not history_path.exists():
            return 0
        deleted = 0
        with self._locked_file(history_path, "r+", exclusive=True) as fh:
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
                if row_id and row_id in record_ids:
                    deleted += 1
                    continue
                kept_lines.append(raw)

            fh.seek(0)
            fh.truncate()
            if kept_lines:
                fh.write("\n".join(kept_lines) + "\n")
            self._flush_and_fsync(fh)
        return deleted

    def _prune_curated_facts_for_ids(self, curated_path: Path | None, record_ids: set[str]) -> int:
        if not record_ids or curated_path is None or not curated_path.exists():
            return 0
        facts = self._read_curated_facts_from(curated_path)
        kept_facts: list[dict[str, object]] = []
        deleted = 0
        for fact in facts:
            row_id = str(fact.get("id", "")).strip()
            if row_id and row_id in record_ids:
                deleted += 1
                continue
            kept_facts.append(fact)
        self._write_curated_facts_to(curated_path, kept_facts)
        return deleted

    def _prune_item_and_category_layers_in_scope(self, scope: dict[str, Path], record_ids: set[str]) -> int:
        if not record_ids or not scope["items"].exists():
            return 0
        deleted = 0
        for item_file in scope["items"].glob("*.json"):
            try:
                payload = json.loads(item_file.read_text(encoding="utf-8") or "{}")
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            category = str(payload.get("category", item_file.stem) or item_file.stem)
            rows = payload.get("items", [])
            if not isinstance(rows, list):
                continue
            kept: list[dict[str, Any]] = []
            removed_here = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_id = str(row.get("id", "")).strip()
                if row_id and row_id in record_ids:
                    removed_here += 1
                    continue
                kept.append(row)
            if removed_here <= 0:
                continue
            deleted += removed_here
            updated_payload = {
                "version": int(payload.get("version", 1) or 1),
                "category": category,
                "updated_at": self._utcnow_iso(),
                "items": kept,
            }
            self._atomic_write_text_locked(item_file, json.dumps(updated_payload, ensure_ascii=False, indent=2) + "\n")
            self._update_scope_category_summary_file(scope, category)
        return deleted

    def _prune_resource_layer_for_ids_in_scope(self, scope: dict[str, Path], record_ids: set[str]) -> int:
        if not record_ids or not scope["resources"].exists():
            return 0
        deleted = 0
        for resource_file in scope["resources"].glob("conv_*.jsonl"):
            try:
                with self._locked_file(resource_file, "r+", exclusive=True) as fh:
                    lines = fh.read().splitlines()
                    kept_lines: list[str] = []
                    for line in lines:
                        raw = line.strip()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            kept_lines.append(raw)
                            continue
                        if not isinstance(payload, dict):
                            kept_lines.append(raw)
                            continue
                        row_id = str(payload.get("id", "")).strip()
                        if row_id and row_id in record_ids:
                            deleted += 1
                            continue
                        kept_lines.append(raw)
                    fh.seek(0)
                    fh.truncate()
                    if kept_lines:
                        fh.write("\n".join(kept_lines) + "\n")
                    self._flush_and_fsync(fh)
            except Exception:
                continue
        return deleted

    def _delete_records_by_ids_in_scope(self, scope: dict[str, Path], record_ids: set[str]) -> dict[str, int]:
        history_deleted = self._prune_history_records_for_ids(scope["history"], record_ids)
        curated_deleted = self._prune_curated_facts_for_ids(scope.get("curated"), record_ids)
        if scope["root"] == self.memory_home:
            layer_deleted = self._prune_item_and_category_layers(record_ids)
            layer_deleted += self._prune_resource_layer_for_ids(record_ids)
        else:
            layer_deleted = self._prune_item_and_category_layers_in_scope(scope, record_ids)
            layer_deleted += self._prune_resource_layer_for_ids_in_scope(scope, record_ids)
        return {
            "history_deleted": int(history_deleted),
            "curated_deleted": int(curated_deleted),
            "layer_deleted": int(layer_deleted),
        }

    def _delete_records_by_ids(self, record_ids: set[str]) -> dict[str, int | list[str]]:
        if not record_ids:
            return {
                "deleted_ids": [],
                "history_deleted": 0,
                "curated_deleted": 0,
                "embeddings_deleted": 0,
                "layer_deleted": 0,
                "backend_deleted": 0,
                "deleted_count": 0,
            }

        history_deleted = 0
        curated_deleted = 0
        embeddings_deleted = 0
        backend_deleted = 0
        layer_deleted = 0

        try:
            for scope in self._iter_existing_scopes():
                deleted = self._delete_records_by_ids_in_scope(scope, record_ids)
                history_deleted += int(deleted.get("history_deleted", 0) or 0)
                curated_deleted += int(deleted.get("curated_deleted", 0) or 0)
                layer_deleted += int(deleted.get("layer_deleted", 0) or 0)
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

        try:
            embeddings_deleted = self._prune_embeddings_for_ids(record_ids)
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

        try:
            backend_deleted = int(self.backend.delete_layer_records(record_ids) or 0)
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

        deleted_ids = sorted(record_ids)
        return {
            "deleted_ids": deleted_ids,
            "history_deleted": history_deleted,
            "curated_deleted": curated_deleted,
            "embeddings_deleted": embeddings_deleted,
            "layer_deleted": layer_deleted,
            "backend_deleted": backend_deleted,
            "deleted_count": len(deleted_ids),
        }

    def _cleanup_expired_ephemeral_records(self) -> int:
        privacy = self._privacy_settings()
        raw_categories = privacy.get("ephemeral_categories", [])
        if not isinstance(raw_categories, list):
            return 0
        categories = {str(item or "").strip().lower() for item in raw_categories if str(item or "").strip()}
        if not categories:
            return 0
        try:
            ttl_days = int(privacy.get("ephemeral_ttl_days", 0) or 0)
        except Exception:
            ttl_days = 0
        if ttl_days <= 0:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        expired_ids: set[str] = set()

        for scope in self._iter_existing_scopes():
            history_path = scope["history"]
            if history_path.exists():
                for row in self._read_history_records_from(history_path):
                    row_id = str(row.id or "").strip()
                    if not row_id:
                        continue
                    if str(row.category or "context").strip().lower() not in categories:
                        continue
                    if self._parse_iso_timestamp(str(row.created_at or "")) < cutoff:
                        expired_ids.add(row_id)

            curated_path = scope.get("curated")
            if curated_path is None or not curated_path.exists():
                continue
            for row in self._read_curated_facts_from(curated_path):
                row_id = str(row.get("id", "")).strip()
                if not row_id:
                    continue
                if str(row.get("category", "context") or "context").strip().lower() not in categories:
                    continue
                if self._parse_iso_timestamp(str(row.get("created_at", "") or "")) < cutoff:
                    expired_ids.add(row_id)

        if not expired_ids:
            return 0

        deleted = self._delete_records_by_ids(expired_ids)
        deleted_count = int(deleted.get("deleted_count", 0) or 0)
        if deleted_count > 0:
            self._diagnostics["privacy_ttl_deleted"] = int(self._diagnostics["privacy_ttl_deleted"]) + deleted_count
            self._append_privacy_audit_event(
                action="ttl_cleanup",
                reason="ephemeral_ttl_expired",
                metadata={
                    "deleted_count": deleted_count,
                    "ttl_days": ttl_days,
                    "categories": sorted(categories),
                },
            )
        return deleted_count

    def add(
        self,
        text: str,
        *,
        source: str = "user",
        raw_resource_text: str | None = None,
        user_id: str = "default",
        shared: bool = False,
        modality: str = "text",
        metadata: dict[str, Any] | None = None,
        reasoning_layer: str | None = None,
        confidence: float | None = None,
        memory_type: str | None = None,
        happened_at: str | None = None,
        decay_rate: float | None = None,
    ) -> MemoryRecord:
        clean = text.strip()
        if not clean:
            raise ValueError("memory text must not be empty")
        clean_user = self._normalize_user_id(user_id)
        category = self._categorize_memory(clean, source)
        memory_basis = str(raw_resource_text or clean)
        resolved_memory_type = self._normalize_memory_type(memory_type or self._infer_memory_type(memory_basis, source, category=category))
        resolved_happened_at = str(happened_at or self._infer_happened_at(memory_basis) or "")
        resolved_decay_rate = self._normalize_decay_rate(
            decay_rate,
            default=self._default_decay_rate(
                memory_type=resolved_memory_type,
                category=category,
                happened_at=resolved_happened_at,
            ),
        )
        reinforced_at = datetime.now(timezone.utc).isoformat()
        scope_key = self._memory_scope_key(user_id=clean_user, shared=shared)
        resolved_metadata = self._prepare_memory_metadata(
            text=memory_basis,
            source=source,
            metadata=metadata,
            memory_type=resolved_memory_type,
            happened_at=resolved_happened_at,
        )
        resolved_metadata = self._seed_reinforcement_metadata(
            resolved_metadata,
            source=source,
            scope_key=scope_key,
            reinforced_at=reinforced_at,
        )
        row = MemoryRecord(
            id=uuid.uuid4().hex,
            text=clean,
            source=source,
            created_at=reinforced_at,
            category=category,
            user_id=clean_user,
            layer=MemoryLayer.ITEM.value,
            reasoning_layer=self._normalize_reasoning_layer(reasoning_layer),
            modality=str(modality or "text").strip().lower() or "text",
            confidence=self._normalize_confidence(confidence, default=1.0),
            decay_rate=resolved_decay_rate,
            emotional_tone=self._detect_emotional_tone(clean) if self.emotional_tracking else "neutral",
            memory_type=resolved_memory_type,
            happened_at=resolved_happened_at,
            metadata=resolved_metadata,
        )
        content_hash = self._metadata_content_hash(row.metadata) or self._memory_content_hash(memory_basis, resolved_memory_type)
        raw_text = str(raw_resource_text or clean)

        if shared or clean_user != "default":
            scope = self._scope_paths(user_id=clean_user, shared=shared)
            self._ensure_scope_paths(scope)
            row, created_new = self._append_or_reinforce_history_record(
                scope["history"],
                row,
                content_hash=content_hash,
                scope_key=scope_key,
                source=source,
                reinforced_at=reinforced_at,
            )
            try:
                if created_new:
                    self._persist_layer_artifacts_to_scope(scope, row, raw_resource_text=raw_text)
                else:
                    self._upsert_item_layer_in_scope(scope, row)
            except Exception:
                pass

            mirrored_created = bool(created_new)
            mirrored = self._upsert_history_record_by_id(self.history_path, row, append_if_missing=created_new)
            if not mirrored and not created_new:
                mirrored = self._upsert_history_record_by_id(self.history_path, row, append_if_missing=True)
                mirrored_created = bool(mirrored)
            try:
                if mirrored_created:
                    self._persist_layer_artifacts(record=row, raw_resource_text=raw_text)
                else:
                    self._upsert_item_layer(row)
            except Exception:
                pass
        else:
            row, created_new = self._append_or_reinforce_history_record(
                self.history_path,
                row,
                content_hash=content_hash,
                scope_key=scope_key,
                source=source,
                reinforced_at=reinforced_at,
            )
            try:
                if created_new:
                    self._persist_layer_artifacts(record=row, raw_resource_text=raw_text)
                else:
                    self._upsert_item_layer(row)
            except Exception:
                pass

        if created_new:
            self._diagnostics["reinforcement_creates"] = int(self._diagnostics["reinforcement_creates"]) + 1
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
        else:
            self._diagnostics["reinforcement_hits"] = int(self._diagnostics["reinforcement_hits"]) + 1
        self._update_profile_from_record(row)
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
            row.text = self._decrypt_text_for_category(str(row.text or ""), row.category)
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
            self._atomic_write_text_locked(self.history_path, rewritten)
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
                reasoning_layer=self._normalize_reasoning_layer(item.get("reasoning_layer", item.get("reasoningLayer", "fact"))),
                confidence=self._normalize_confidence(item.get("confidence", 1.0), default=1.0),
                decay_rate=self._normalize_decay_rate(item.get("decay_rate", item.get("decayRate", self._default_decay_rate(memory_type=item.get("memory_type", item.get("memoryType", "knowledge")))))),
                memory_type=self._normalize_memory_type(item.get("memory_type", item.get("memoryType", "knowledge"))),
                happened_at=str(item.get("happened_at", item.get("happenedAt", "")) or ""),
                metadata=self._normalize_memory_metadata(item.get("metadata", {})),
            )
            for item in rows
            if str(item.get("text", "")).strip()
        ]

    def list_recent_candidates(
        self,
        *,
        source: str = "",
        ref_prefix: str = "",
        limit: int = 10,
        max_scan: int = 500,
    ) -> list[MemoryRecord]:
        bounded_limit = max(1, int(limit or 1))
        bounded_scan = max(bounded_limit, min(max(1, int(max_scan or bounded_limit)), 5000))
        clean_source = str(source or "").strip()
        clean_prefix = self._normalize_prefix(ref_prefix)

        out: list[MemoryRecord] = []
        seen_ids: set[str] = set()

        def _accept(row: MemoryRecord | None) -> bool:
            if row is None:
                return False
            row_id = str(row.id or "").strip()
            if not row_id or row_id in seen_ids:
                return False
            if clean_prefix and not self._normalize_prefix(row_id).startswith(clean_prefix):
                return False
            if clean_source and str(row.source or "") != clean_source:
                return False
            seen_ids.add(row_id)
            out.append(row)
            return len(out) >= bounded_limit

        try:
            backend_rows = self.backend.fetch_layer_records(layer=MemoryLayer.ITEM.value, limit=bounded_scan)
        except Exception:
            backend_rows = []
        for row in backend_rows:
            if not isinstance(row, dict):
                continue
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            candidate = self._record_from_payload(payload)
            if candidate is None:
                continue
            candidate.text = self._decrypt_text_for_category(str(candidate.text or ""), candidate.category)
            if _accept(candidate):
                return out

        with self._locked_file(self.history_path, "r", exclusive=False) as fh:
            recent_lines = deque(fh, maxlen=bounded_scan)
        for line in reversed(list(recent_lines)):
            raw = str(line or "").strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            candidate = self._record_from_payload(payload)
            if candidate is None:
                continue
            candidate.text = self._decrypt_text_for_category(str(candidate.text or ""), candidate.category)
            if _accept(candidate):
                return out

        for item in self._read_curated_facts():
            candidate = self._record_from_payload(item)
            if candidate is None:
                continue
            if _accept(candidate):
                return out

        out.sort(key=self._record_sort_key, reverse=True)
        return out[:bounded_limit]

    async def memorize(
        self,
        *,
        text: str | None = None,
        messages: Iterable[dict[str, str]] | None = None,
        source: str = "session",
        user_id: str = "default",
        shared: bool = False,
        include_shared: bool = False,
        file_path: str | None = None,
        url: str | None = None,
        modality: str = "text",
        metadata: dict[str, Any] | None = None,
        reasoning_layer: str | None = None,
        confidence: float | None = None,
        memory_type: str | None = None,
        happened_at: str | None = None,
        decay_rate: float | None = None,
    ) -> dict[str, Any]:
        _ = include_shared
        try:
            await asyncio.to_thread(self._cleanup_expired_ephemeral_records)
        except Exception as exc:
            self._diagnostics["last_error"] = str(exc)

        if messages is not None:
            joined_text = "\n".join(str(item.get("content", "") or "") for item in messages if isinstance(item, dict))
            blocked_reason = self._privacy_block_reason(joined_text) if joined_text else None
            if blocked_reason is not None:
                self._append_privacy_audit_event(
                    action="memorize_skipped",
                    reason=blocked_reason,
                    source=source,
                    metadata={"mode": "consolidate"},
                )
                return {"status": "skipped", "mode": "consolidate", "record": None}
            record = await asyncio.to_thread(
                self.consolidate,
                messages,
                source=source,
                user_id=user_id,
                shared=shared,
                metadata=metadata,
                reasoning_layer=reasoning_layer,
                confidence=confidence,
                memory_type=memory_type,
                happened_at=happened_at,
                decay_rate=decay_rate,
            )
            if record is None:
                return {"status": "skipped", "mode": "consolidate", "record": None}
            return {"status": "ok", "mode": "consolidate", "record": asdict(record)}

        resolved_modality = str(modality or "text").strip().lower() or "text"
        clean = str(text or "").strip()
        if not clean and file_path:
            clean = await asyncio.to_thread(
                self._memory_text_from_file,
                file_path,
                modality=resolved_modality,
                metadata=metadata,
            )
        if not clean and url:
            clean = await asyncio.to_thread(
                self._memory_text_from_url,
                url,
                modality=resolved_modality,
                metadata=metadata,
            )
        if not clean:
            raise ValueError("text or messages is required")
        blocked_reason = self._privacy_block_reason(clean)
        if blocked_reason is not None:
            self._append_privacy_audit_event(
                action="memorize_skipped",
                reason=blocked_reason,
                source=source,
                metadata={"mode": "add"},
            )
            return {"status": "skipped", "mode": "add", "record": None}
        record = await asyncio.to_thread(
            self.add,
            clean,
            source=source,
            user_id=user_id,
            shared=shared,
            modality=resolved_modality,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
        )
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
            "reasoning_layer": MemoryStore._normalize_reasoning_layer(getattr(row, "reasoning_layer", "fact")),
            "modality": str(row.modality or "text"),
            "updated_at": str(row.updated_at or ""),
            "confidence": MemoryStore._normalize_confidence(getattr(row, "confidence", 1.0), default=1.0),
            "decay_rate": float(row.decay_rate),
            "emotional_tone": str(row.emotional_tone or "neutral"),
            "memory_type": MemoryStore._normalize_memory_type(getattr(row, "memory_type", "knowledge")),
            "happened_at": str(getattr(row, "happened_at", "") or ""),
            "metadata": MemoryStore._normalize_memory_metadata(getattr(row, "metadata", {})),
        }

    def _resolve_retrieval_scopes(self, *, user_id: str, include_shared: bool) -> list[dict[str, Path]]:
        clean_user = self._normalize_user_id(user_id or "default")
        scopes: list[dict[str, Path]] = []
        scopes.append(self._scope_paths(user_id=clean_user, shared=False))
        if clean_user != "default" and include_shared and self.shared_opt_in(clean_user):
            scopes.append(self._scope_paths(shared=True))
        for scope in scopes:
            self._ensure_scope_paths(scope)
        return scopes

    def _collect_retrieval_records(
        self,
        *,
        user_id: str,
        include_shared: bool,
        session_id: str,
        reasoning_layers: Iterable[str] | None,
        min_confidence: float | None,
        filters: dict[str, Any] | None,
    ) -> tuple[list[MemoryRecord], dict[str, float], dict[str, int], list[dict[str, Path]], bool]:
        clean_user = self._normalize_user_id(user_id or "default")
        reasoning_filter = self._normalize_reasoning_layers_filter(reasoning_layers)
        min_conf_filter = self._normalize_confidence(min_confidence, default=0.0) if min_confidence is not None else None
        normalized_filters = self._normalize_retrieval_filters(filters)
        scopes = self._resolve_retrieval_scopes(user_id=clean_user, include_shared=include_shared)

        records: list[MemoryRecord] = []
        curated_importance: dict[str, float] = {}
        curated_mentions: dict[str, int] = {}

        for scope in scopes:
            scope_root = scope["root"]
            scope_user_id = "shared" if scope_root == self.shared_path else clean_user
            curated_rows = self._read_curated_facts_from(scope["curated"])
            for item in curated_rows:
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                row = MemoryRecord(
                    id=str(item.get("id", "")),
                    text=text,
                    source=str(item.get("source", "curated")),
                    created_at=str(item.get("created_at", "")),
                    category=str(item.get("category", "context") or "context"),
                    user_id=scope_user_id,
                    reasoning_layer=self._normalize_reasoning_layer(item.get("reasoning_layer", item.get("reasoningLayer", "fact"))),
                    modality=str(item.get("modality", "text") or "text"),
                    confidence=self._normalize_confidence(item.get("confidence", 1.0), default=1.0),
                    decay_rate=self._normalize_decay_rate(item.get("decay_rate", item.get("decayRate", self._default_decay_rate(memory_type=item.get("memory_type", item.get("memoryType", "knowledge")))))),
                    memory_type=self._normalize_memory_type(item.get("memory_type", item.get("memoryType", "knowledge"))),
                    happened_at=str(item.get("happened_at", item.get("happenedAt", "")) or ""),
                    metadata=self._normalize_memory_metadata(item.get("metadata", {})),
                )
                records.append(row)
                curated_importance[row.id] = float(item.get("importance", 1.0) or 1.0)
                try:
                    curated_mentions[row.id] = int(item.get("mentions", 1) or 1)
                except Exception:
                    curated_mentions[row.id] = 1

            records.extend(self._read_history_records_from(scope["history"]))

        records = self._apply_retrieval_filters(records, normalized_filters)
        if reasoning_filter:
            records = [row for row in records if self._normalize_reasoning_layer(row.reasoning_layer) in reasoning_filter]
        if min_conf_filter is not None:
            records = [row for row in records if self._normalize_confidence(row.confidence, default=1.0) >= min_conf_filter]
        if session_id:
            records = [row for row in records if self._working_episode_visible_in_session(row, session_id=session_id)]

        semantic_enabled = bool(self.semantic_enabled and bool(records))
        return records, curated_importance, curated_mentions, scopes, semantic_enabled

    @classmethod
    def _rewrite_retrieval_query(cls, query: str) -> str:
        raw = cls._compact_whitespace(query)
        if not raw:
            return ""
        query_entities = cls._extract_entities(raw)
        tokens = cls._tokens(raw)
        if not tokens:
            return raw

        preserved = [token for token in tokens if token not in cls._RETRIEVAL_REWRITE_STOPWORDS]
        rewritten = " ".join(preserved).strip() if preserved else raw

        for values in query_entities.values():
            for value in values:
                clean_value = cls._compact_whitespace(value)
                if clean_value and clean_value.lower() not in rewritten.lower():
                    rewritten = f"{rewritten} {clean_value}".strip()

        if not rewritten:
            return raw
        if len(rewritten) + 8 < len(raw):
            return rewritten
        return raw

    @classmethod
    def _query_coverage(cls, query: str, texts: list[str]) -> dict[str, Any]:
        q_tokens = set(cls._tokens(query))
        if not q_tokens:
            return {"covered_tokens": [], "missing_tokens": [], "coverage_ratio": 0.0, "entity_score": 0.0, "temporal_match": False}

        covered: set[str] = set()
        best_entity_score = 0.0
        temporal_match = False
        query_entities = cls._extract_entities(query)
        temporal_query = cls._query_has_temporal_intent(query)

        for text in texts:
            covered.update(q_tokens.intersection(cls._tokens(text)))
            best_entity_score = max(best_entity_score, cls._entity_match_score(query_entities, cls._extract_entities(text)))
            if temporal_query and cls._memory_has_temporal_markers(text):
                temporal_match = True

        coverage_ratio = float(len(covered)) / float(len(q_tokens)) if q_tokens else 0.0
        missing_tokens = sorted(q_tokens.difference(covered))
        return {
            "covered_tokens": sorted(covered),
            "missing_tokens": missing_tokens,
            "coverage_ratio": round(max(0.0, min(1.0, coverage_ratio)), 6),
            "entity_score": round(max(0.0, best_entity_score), 6),
            "temporal_match": temporal_match,
        }

    def _evaluate_retrieval_sufficiency(self, query: str, texts: list[str], *, stage: str) -> dict[str, Any]:
        if stage == "category":
            has_signal = bool(texts)
            return {
                "stage": stage,
                "sufficient": False,
                "reason": "need_item_level_recall" if has_signal else "no_category_signal",
                "covered_tokens": [],
                "missing_tokens": sorted(set(self._tokens(query))),
                "coverage_ratio": 0.0,
                "entity_score": 0.0,
                "temporal_match": False,
            }

        coverage = self._query_coverage(query, texts)
        coverage_ratio = float(coverage["coverage_ratio"])
        entity_score = float(coverage["entity_score"])
        temporal_match = bool(coverage["temporal_match"])
        temporal_query = self._query_has_temporal_intent(query)
        sufficient = bool(
            coverage_ratio >= 0.8
            or entity_score >= 0.3
            or (temporal_query and temporal_match and coverage_ratio >= 0.5)
        )
        if not texts:
            reason = f"no_{stage}_hits"
        elif sufficient:
            if coverage_ratio >= 0.8:
                reason = f"{stage}_coverage_sufficient"
            elif entity_score >= 0.3:
                reason = f"{stage}_entity_match_sufficient"
            else:
                reason = f"{stage}_temporal_match_sufficient"
        else:
            reason = f"{stage}_coverage_incomplete"
        coverage["stage"] = stage
        coverage["sufficient"] = sufficient
        coverage["reason"] = reason
        return coverage

    def _retrieve_category_hits(self, query: str, records: list[MemoryRecord], *, limit: int) -> list[dict[str, Any]]:
        q_tokens = set(self._tokens(query))
        query_entities = self._extract_entities(query)
        temporal_query = self._query_has_temporal_intent(query)
        by_category: dict[str, dict[str, Any]] = {}

        for row in records:
            category = str(row.category or "context")
            text_tokens = set(self._tokens(row.text))
            overlap = len(q_tokens.intersection(text_tokens))
            entity_score = self._entity_match_score(query_entities, self._extract_entities(row.text))
            category_overlap = len(q_tokens.intersection(self._tokens(category))) * 0.35
            type_overlap = len(q_tokens.intersection(self._tokens(row.memory_type))) * 0.25
            temporal_bonus = 0.15 if temporal_query and (row.happened_at or self._memory_has_temporal_markers(row.text)) else 0.0
            salience_bonus = self._salience_boost(row.metadata) * 0.5
            score = float(overlap) + entity_score + category_overlap + type_overlap + temporal_bonus + salience_bonus
            if score <= 0.0:
                continue

            bucket = by_category.setdefault(
                category,
                {
                    "category": category,
                    "score": 0.0,
                    "count": 0,
                    "sample_text": "",
                    "memory_types": set(),
                    "sources": set(),
                    "top_score": 0.0,
                },
            )
            bucket["score"] = float(bucket["score"]) + score
            bucket["count"] = int(bucket["count"]) + 1
            bucket["memory_types"].add(str(row.memory_type or "knowledge"))
            bucket["sources"].add(str(row.source or "unknown"))
            if score >= float(bucket["top_score"]):
                bucket["top_score"] = score
                bucket["sample_text"] = str(row.text or "").strip()[:160]

        ranked = sorted(
            by_category.values(),
            key=lambda item: (float(item["score"]), int(item["count"]), str(item["category"])),
            reverse=True,
        )
        out: list[dict[str, Any]] = []
        for item in ranked[: max(1, limit)]:
            out.append(
                {
                    "category": str(item["category"]),
                    "score": round(float(item["score"]), 6),
                    "count": int(item["count"]),
                    "sample_text": str(item["sample_text"]),
                    "memory_types": sorted(str(value) for value in item["memory_types"]),
                    "sources": sorted(str(value) for value in item["sources"]),
                }
            )
        return out

    @staticmethod
    def _filter_records_to_categories(records: list[MemoryRecord], categories: list[str]) -> list[MemoryRecord]:
        allowed = {str(item or "").strip().lower() for item in categories if str(item or "").strip()}
        if not allowed:
            return list(records)
        return [row for row in records if str(row.category or "context").strip().lower() in allowed]

    def _retrieve_resource_hits(
        self,
        scopes: list[dict[str, Path]],
        *,
        record_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        wanted_ids = {str(item or "").strip() for item in record_ids if str(item or "").strip()}
        if not wanted_ids:
            return []

        out: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for scope in scopes:
            resources_root = scope["resources"]
            if not resources_root.exists():
                continue
            for resource_file in sorted(resources_root.glob("conv_*.jsonl"), reverse=True):
                try:
                    with self._locked_file(resource_file, "r", exclusive=False) as fh:
                        lines = fh.read().splitlines()
                except Exception:
                    continue
                for line in reversed(lines):
                    raw = str(line or "").strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    row_id = str(payload.get("id", "")).strip()
                    if not row_id or row_id not in wanted_ids or row_id in seen_ids:
                        continue
                    category = str(payload.get("category", "context") or "context")
                    text = self._decrypt_text_for_category(str(payload.get("text", "") or ""), category)
                    out.append(
                        {
                            "id": row_id,
                            "text": text,
                            "source": str(payload.get("source", "") or ""),
                            "category": category,
                            "created_at": str(payload.get("created_at", "") or ""),
                            "layer": MemoryLayer.RESOURCE.value,
                        }
                    )
                    seen_ids.add(row_id)
                    if len(out) >= limit:
                        return out
        return out

    def _build_progressive_retrieval_payload(
        self,
        query: str,
        *,
        limit: int,
        user_id: str,
        session_id: str,
        include_shared: bool,
        reasoning_layers: Iterable[str] | None,
        min_confidence: float | None,
        filters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        rewritten_query = self._rewrite_retrieval_query(query)
        active_query = rewritten_query or query
        records, curated_importance, curated_mentions, scopes, semantic_enabled = self._collect_retrieval_records(
            user_id=user_id,
            include_shared=include_shared,
            session_id=session_id,
            reasoning_layers=reasoning_layers,
            min_confidence=min_confidence,
            filters=filters,
        )

        category_hits = self._retrieve_category_hits(active_query, records, limit=max(3, min(6, limit)))
        selected_categories = [str(item.get("category", "")) for item in category_hits[:3] if str(item.get("category", ""))]
        category_sufficiency = self._evaluate_retrieval_sufficiency(
            active_query,
            [str(item.get("sample_text", "") or "") for item in category_hits if str(item.get("sample_text", "") or "")],
            stage="category",
        )

        candidate_records = self._filter_records_to_categories(records, selected_categories)
        if not candidate_records:
            candidate_records = list(records)
        item_records = self._rank_records(
            active_query,
            candidate_records,
            curated_importance=curated_importance,
            curated_mentions=curated_mentions,
            limit=limit,
            semantic_enabled=semantic_enabled,
            session_id=session_id,
        )
        item_hits = [self._serialize_hit(row) for row in item_records]
        item_sufficiency = self._evaluate_retrieval_sufficiency(
            active_query,
            [str(row.text or "") for row in item_records],
            stage="item",
        )

        resource_hits: list[dict[str, Any]] = []
        resource_sufficiency = {
            "stage": "resource",
            "sufficient": False,
            "reason": "resource_stage_skipped" if item_sufficiency["sufficient"] else "no_resource_hits",
            "covered_tokens": [],
            "missing_tokens": list(item_sufficiency.get("missing_tokens", [])),
            "coverage_ratio": 0.0,
            "entity_score": 0.0,
            "temporal_match": False,
        }
        if item_records and not item_sufficiency["sufficient"]:
            resource_hits = self._retrieve_resource_hits(
                scopes,
                record_ids=[str(row.id or "") for row in item_records],
                limit=max(1, limit),
            )
            combined_texts = [str(row.text or "") for row in item_records] + [str(item.get("text", "") or "") for item in resource_hits]
            resource_sufficiency = self._evaluate_retrieval_sufficiency(active_query, combined_texts, stage="resource")
        episodic_digest = self._synthesize_visible_episode_digest(
            query=active_query,
            session_id=session_id,
            records=candidate_records,
            curated_importance=curated_importance,
            curated_mentions=curated_mentions,
            semantic_enabled=semantic_enabled,
            limit=limit,
        )

        stages = [
            {
                "stage": "category",
                "query": active_query,
                "count": len(category_hits),
                "selected_categories": selected_categories,
                "sufficiency": category_sufficiency,
            },
            {
                "stage": "item",
                "query": active_query,
                "count": len(item_hits),
                "selected_categories": selected_categories,
                "sufficiency": item_sufficiency,
            },
        ]
        if resource_hits or not item_sufficiency["sufficient"]:
            stages.append(
                {
                    "stage": "resource",
                    "query": active_query,
                    "count": len(resource_hits),
                    "sufficiency": resource_sufficiency,
                }
            )

        return {
            "query": query,
            "rewritten_query": rewritten_query,
            "active_query": active_query,
            "hits": item_hits,
            "category_hits": category_hits,
            "resource_hits": resource_hits,
            "progressive": {
                "route": "category_item_resource",
                "selected_categories": selected_categories,
                "category_sufficiency": category_sufficiency,
                "item_sufficiency": item_sufficiency,
                "resource_sufficiency": resource_sufficiency,
                "stages": stages,
            },
            "episodic_digest": episodic_digest,
        }

    def _refine_hits_with_llm(
        self,
        query: str,
        hits: list[dict[str, Any]],
        *,
        category_hits: list[dict[str, Any]] | None = None,
        resource_hits: list[dict[str, Any]] | None = None,
    ) -> dict[str, str] | None:
        if not hits:
            return {"answer": "", "next_step_query": ""}
        category_payload = category_hits if isinstance(category_hits, list) else []
        resource_payload = resource_hits if isinstance(resource_hits, list) else []
        prompt = (
            "Use os trechos de memoria abaixo para responder de forma objetiva. "
            "Se os trechos nao forem suficientes, diga isso explicitamente. "
            "Responda APENAS em JSON valido com as chaves: answer (string) e next_step_query (string opcional).\n\n"
            f"PERGUNTA:\n{query}\n\n"
            f"CATEGORIAS:\n{json.dumps(category_payload, ensure_ascii=False)}\n\n"
            f"MEMORIAS:\n{json.dumps(hits, ensure_ascii=False)}\n\n"
            f"RECURSOS:\n{json.dumps(resource_payload, ensure_ascii=False)}"
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
        content = content.strip()
        if not content:
            return {"answer": "", "next_step_query": ""}
        try:
            parsed = json.loads(content)
        except Exception:
            return {"answer": content, "next_step_query": ""}
        if not isinstance(parsed, dict):
            return {"answer": content, "next_step_query": ""}
        answer = str(parsed.get("answer", "") or "").strip()
        next_step = str(parsed.get("next_step_query", "") or "").strip()
        return {"answer": answer, "next_step_query": next_step}

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        method: str = "rag",
        user_id: str = "",
        session_id: str = "",
        include_shared: bool = False,
        reasoning_layers: Iterable[str] | None = None,
        min_confidence: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_query = str(query or "").strip()
        if not clean_query:
            raise ValueError("query is required")
        bounded_limit = max(1, int(limit or 1))
        resolved_user = user_id or "default"
        progressive = await asyncio.to_thread(
            self._build_progressive_retrieval_payload,
            clean_query,
            user_id=resolved_user,
            session_id=session_id,
            limit=bounded_limit,
            include_shared=include_shared,
            reasoning_layers=reasoning_layers,
            min_confidence=min_confidence,
            filters=filters,
        )
        hits = progressive["hits"]
        category_hits = progressive["category_hits"]
        resource_hits = progressive["resource_hits"]
        rewritten_query = str(progressive.get("rewritten_query", "") or "")

        rag_payload: dict[str, Any] = {
            "status": "ok",
            "method": "rag",
            "query": clean_query,
            "rewritten_query": rewritten_query,
            "limit": bounded_limit,
            "count": len(hits),
            "hits": hits,
            "category_hits": category_hits,
            "resource_hits": resource_hits,
            "episodic_digest": progressive.get("episodic_digest"),
            "metadata": {
                "fallback_to_rag": False,
                "progressive": progressive["progressive"],
                "episodic_digest": progressive.get("episodic_digest"),
            },
        }
        normalized_method = str(method or "rag").strip().lower()
        if normalized_method == "rag":
            return rag_payload
        if normalized_method != "llm":
            raise ValueError("method must be 'rag' or 'llm'")

        llm_refinement = await asyncio.to_thread(
            self._refine_hits_with_llm,
            clean_query,
            hits,
            category_hits=category_hits,
            resource_hits=resource_hits,
        )
        if llm_refinement is None:
            rag_payload["method"] = "llm"
            rag_payload["metadata"] = {
                "fallback_to_rag": True,
                "progressive": progressive["progressive"],
                "episodic_digest": progressive.get("episodic_digest"),
            }
            rag_payload["answer"] = ""
            rag_payload["next_step_query"] = ""
            return rag_payload

        return {
            "status": "ok",
            "method": "llm",
            "query": clean_query,
            "rewritten_query": rewritten_query,
            "limit": bounded_limit,
            "count": len(hits),
            "hits": hits,
            "category_hits": category_hits,
            "resource_hits": resource_hits,
            "episodic_digest": progressive.get("episodic_digest"),
            "answer": str(llm_refinement.get("answer", "") or ""),
            "next_step_query": str(llm_refinement.get("next_step_query", "") or ""),
            "metadata": {
                "fallback_to_rag": False,
                "progressive": progressive["progressive"],
                "episodic_digest": progressive.get("episodic_digest"),
            },
        }

    def _rank_records(
        self,
        query: str,
        records: list[MemoryRecord],
        *,
        curated_importance: dict[str, float],
        curated_mentions: dict[str, int],
        limit: int,
        semantic_enabled: bool,
        session_id: str = "",
    ) -> list[MemoryRecord]:
        if not records:
            return []
        q_tokens = self._tokens(query)
        query_entities = self._extract_entities(query)
        reasoning_boosts = self._reasoning_intent_boosts(query)
        query_has_temporal_intent = self._query_has_temporal_intent(query)
        if not q_tokens:
            return records[-limit:][::-1]

        corpus_tokens = [self._tokens(item.text) for item in records]
        corpus_entities = [self._extract_entities(item.text) for item in records]
        qset = set(q_tokens)

        if BM25Okapi is None:
            bm25_scores = [0.0 for _ in records]
        else:
            bm25 = BM25Okapi(corpus_tokens)
            scores = bm25.get_scores(q_tokens)
            bm25_scores = [float(scores[idx]) for idx in range(len(records))]

        semantic_scores = [0.0 for _ in records]
        semantic_active = False
        if semantic_enabled:
            query_embedding = self._generate_embedding(query)
            if query_embedding is not None:
                similarity_hits: list[dict[str, Any]] = []
                try:
                    similarity_hits = self.backend.query_similar_embeddings(
                        query_embedding,
                        record_ids=[row.id for row in records if str(row.id or "").strip()],
                        limit=max(1, len(records)),
                    )
                except Exception:
                    similarity_hits = []

                if similarity_hits:
                    score_by_id: dict[str, float] = {}
                    for hit in similarity_hits:
                        if not isinstance(hit, dict):
                            continue
                        row_id = str(hit.get("record_id", "")).strip()
                        if not row_id:
                            continue
                        try:
                            score_by_id[row_id] = float(hit.get("score", 0.0) or 0.0)
                        except Exception:
                            continue
                    if score_by_id:
                        for idx, row in enumerate(records):
                            semantic_scores[idx] = score_by_id.get(str(row.id or ""), 0.0)
                        semantic_active = True
                if not semantic_active:
                    embeddings = self._read_embeddings_map()
                    if embeddings:
                        for idx, row in enumerate(records):
                            vector = embeddings.get(row.id)
                            if vector is None:
                                continue
                            semantic_scores[idx] = self._cosine_similarity(query_embedding, vector)
                        semantic_active = True

        scored: list[tuple[float, float, float, int]] = []
        for idx, toks in enumerate(corpus_tokens):
            overlap = len(qset.intersection(toks))
            entity_score = self._entity_match_score(query_entities, corpus_entities[idx])
            curated_boost = 0.0
            if records[idx].source.startswith("curated:"):
                importance = curated_importance.get(records[idx].id, 1.0)
                mentions = curated_mentions.get(records[idx].id, 1)
                curated_boost = 0.75 + min(2.0, importance * 0.25) + min(1.0, mentions * 0.1)
            temporal_score = self._recency_score(self._record_temporal_anchor(records[idx]))
            if query_has_temporal_intent:
                if records[idx].happened_at or self._memory_has_temporal_markers(records[idx].text):
                    temporal_score += self._TEMPORAL_INTENT_MATCH_BOOST
                else:
                    temporal_score -= self._TEMPORAL_INTENT_MISS_PENALTY

            confidence_boost = self._bounded_confidence_score(records[idx].confidence) * self._RANKING_CONFIDENCE_BOOST_MAX
            reasoning_layer = self._normalize_reasoning_layer(getattr(records[idx], "reasoning_layer", "fact"))
            reasoning_boost = reasoning_boosts.get(reasoning_layer, 0.0)
            decay_penalty = self._decay_penalty(records[idx])
            upcoming_boost = self._upcoming_event_boost(records[idx])
            relevance_signal = bool(
                overlap > 0
                or bm25_scores[idx] > 0.0
                or entity_score > 0.0
                or (semantic_active and semantic_scores[idx] > 0.05)
            )
            salience_boost = self._salience_boost(getattr(records[idx], "metadata", {})) if relevance_signal else 0.0
            raw_episodic_boost = self._episodic_session_boost(records[idx], session_id=session_id)
            episodic_boost = raw_episodic_boost if relevance_signal or query_has_temporal_intent else 0.0
            if not relevance_signal and episodic_boost > 0.0 and query_has_temporal_intent:
                relevance_signal = True

            ranking_score = bm25_scores[idx]
            ranking_score += (
                confidence_boost
                + reasoning_boost
                + entity_score
                + salience_boost
                + episodic_boost
                + upcoming_boost
                - decay_penalty
            )
            tie_breaker = (
                temporal_score
                + (confidence_boost * 0.5)
                + reasoning_boost
                + entity_score
                + salience_boost
                + episodic_boost
                + upcoming_boost
                - decay_penalty
            )
            if semantic_active:
                ranking_score = (
                    self._SEMANTIC_BM25_WEIGHT * bm25_scores[idx]
                    + self._SEMANTIC_VECTOR_WEIGHT * semantic_scores[idx]
                    + confidence_boost
                    + reasoning_boost
                    + entity_score
                    + salience_boost
                    + episodic_boost
                    + upcoming_boost
                    - decay_penalty
                )
                tie_breaker = (
                    curated_boost
                    + temporal_score
                    + (confidence_boost * 0.5)
                    + reasoning_boost
                    + entity_score
                    + salience_boost
                    + episodic_boost
                    + upcoming_boost
                    - decay_penalty
                )
                scored.append((float(overlap) + entity_score + episodic_boost, ranking_score, tie_breaker, idx))
            else:
                scored.append((float(overlap) + curated_boost + entity_score + episodic_boost, ranking_score, tie_breaker, idx))

        scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        picked: list[MemoryRecord] = []
        for overlap_score, relevance_score, _tie_breaker, idx in scored:
            if len(picked) >= limit:
                break
            if overlap_score <= 0 and relevance_score <= 0.0:
                continue
            picked.append(records[idx])
        return picked if picked else records[-limit:][::-1]

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        user_id: str = "",
        session_id: str = "",
        include_shared: bool = False,
        reasoning_layers: Iterable[str] | None = None,
        min_confidence: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        bounded_limit = max(1, int(limit or 1))
        clean_user = self._normalize_user_id(user_id or "default")
        reasoning_filter = self._normalize_reasoning_layers_filter(reasoning_layers)
        min_conf_filter = self._normalize_confidence(min_confidence, default=0.0) if min_confidence is not None else None
        normalized_filters = self._normalize_retrieval_filters(filters)

        if clean_user == "default" and not include_shared:
            curated_rows = self._read_curated_facts()
            curated_records = [
                MemoryRecord(
                    id=str(item.get("id", "")),
                    text=str(item.get("text", "")).strip(),
                    source=str(item.get("source", "curated")),
                    created_at=str(item.get("created_at", "")),
                    category=str(item.get("category", "context") or "context"),
                    reasoning_layer=self._normalize_reasoning_layer(item.get("reasoning_layer", item.get("reasoningLayer", "fact"))),
                    modality=str(item.get("modality", "text") or "text"),
                    confidence=self._normalize_confidence(item.get("confidence", 1.0), default=1.0),
                    memory_type=self._normalize_memory_type(item.get("memory_type", item.get("memoryType", "knowledge"))),
                    happened_at=str(item.get("happened_at", item.get("happenedAt", "")) or ""),
                    metadata=self._normalize_memory_metadata(item.get("metadata", {})),
                )
                for item in curated_rows
                if str(item.get("text", "")).strip()
            ]
            curated_importance = {str(item.get("id", "")): float(item.get("importance", 1.0)) for item in curated_rows}
            curated_mentions = {str(item.get("id", "")): int(item.get("mentions", 1)) for item in curated_rows}
            records = curated_records + self.all()
            records = self._apply_retrieval_filters(records, normalized_filters)
            if reasoning_filter:
                records = [row for row in records if self._normalize_reasoning_layer(row.reasoning_layer) in reasoning_filter]
            if min_conf_filter is not None:
                records = [row for row in records if self._normalize_confidence(row.confidence, default=1.0) >= min_conf_filter]
            return self._rank_records(
                query,
                records,
                curated_importance=curated_importance,
                curated_mentions=curated_mentions,
                limit=bounded_limit,
                semantic_enabled=self.semantic_enabled,
                session_id=session_id,
            )

        user_scope = self._scope_paths(user_id=clean_user, shared=False)
        self._ensure_scope_paths(user_scope)
        curated_rows = self._read_curated_facts_from(user_scope["curated"])
        curated_records = [
                MemoryRecord(
                    id=str(item.get("id", "")),
                    text=str(item.get("text", "")).strip(),
                    source=str(item.get("source", "curated")),
                    created_at=str(item.get("created_at", "")),
                    category=str(item.get("category", "context") or "context"),
                    user_id=clean_user,
                    reasoning_layer=self._normalize_reasoning_layer(item.get("reasoning_layer", item.get("reasoningLayer", "fact"))),
                    modality=str(item.get("modality", "text") or "text"),
                    confidence=self._normalize_confidence(item.get("confidence", 1.0), default=1.0),
                    decay_rate=self._normalize_decay_rate(item.get("decay_rate", item.get("decayRate", self._default_decay_rate(memory_type=item.get("memory_type", item.get("memoryType", "knowledge")))))),
                    memory_type=self._normalize_memory_type(item.get("memory_type", item.get("memoryType", "knowledge"))),
                    happened_at=str(item.get("happened_at", item.get("happenedAt", "")) or ""),
                    metadata=self._normalize_memory_metadata(item.get("metadata", {})),
                )
                for item in curated_rows
                if str(item.get("text", "")).strip()
            ]
        history_records = self._read_history_records_from(user_scope["history"])
        records = curated_records + history_records
        curated_importance = {str(item.get("id", "")): float(item.get("importance", 1.0)) for item in curated_rows}
        curated_mentions = {str(item.get("id", "")): int(item.get("mentions", 1)) for item in curated_rows}

        if include_shared and self.shared_opt_in(clean_user):
            shared_scope = self._scope_paths(shared=True)
            self._ensure_scope_paths(shared_scope)
            shared_curated = self._read_curated_facts_from(shared_scope["curated"])
            records.extend(
                MemoryRecord(
                    id=str(item.get("id", "")),
                    text=str(item.get("text", "")).strip(),
                    source=str(item.get("source", "curated:shared")),
                    created_at=str(item.get("created_at", "")),
                    category=str(item.get("category", "context") or "context"),
                    user_id="shared",
                    reasoning_layer=self._normalize_reasoning_layer(item.get("reasoning_layer", item.get("reasoningLayer", "fact"))),
                    modality=str(item.get("modality", "text") or "text"),
                    confidence=self._normalize_confidence(item.get("confidence", 1.0), default=1.0),
                    decay_rate=self._normalize_decay_rate(item.get("decay_rate", item.get("decayRate", self._default_decay_rate(memory_type=item.get("memory_type", item.get("memoryType", "knowledge")))))),
                    memory_type=self._normalize_memory_type(item.get("memory_type", item.get("memoryType", "knowledge"))),
                    happened_at=str(item.get("happened_at", item.get("happenedAt", "")) or ""),
                    metadata=self._normalize_memory_metadata(item.get("metadata", {})),
                )
                for item in shared_curated
                if str(item.get("text", "")).strip()
            )
            records.extend(self._read_history_records_from(shared_scope["history"]))

        records = self._apply_retrieval_filters(records, normalized_filters)
        if reasoning_filter:
            records = [row for row in records if self._normalize_reasoning_layer(row.reasoning_layer) in reasoning_filter]
        if min_conf_filter is not None:
            records = [row for row in records if self._normalize_confidence(row.confidence, default=1.0) >= min_conf_filter]
        if session_id:
            records = [row for row in records if self._working_episode_visible_in_session(row, session_id=session_id)]

        return self._rank_records(
            query,
            records,
            curated_importance=curated_importance,
            curated_mentions=curated_mentions,
            limit=bounded_limit,
            semantic_enabled=bool(self.semantic_enabled and bool(records)),
            session_id=session_id,
        )

    def _consolidate_in_scope(
        self,
        scope: dict[str, Path],
        messages: Iterable[dict[str, str]],
        *,
        source: str,
        user_id: str,
        shared: bool,
        metadata: dict[str, Any] | None = None,
        reasoning_layer: str | None = None,
        confidence: float | None = None,
        memory_type: str | None = None,
        happened_at: str | None = None,
        decay_rate: float | None = None,
    ) -> MemoryRecord | None:
        self._ensure_scope_paths(scope)
        lines = self._extract_consolidation_lines(messages)
        if not lines:
            return None

        source_lines: list[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", "")).strip().lower()
            content = " ".join(str(msg.get("content", "") or "").split())
            if role not in {"user", "assistant"} or not content:
                continue
            source_lines.append(f"{role}: {content}")
        resource_text = "\n".join(source_lines).strip()

        summary_lines = lines[-6:]
        signature = self._chunk_signature(summary_lines)
        repeated_count = 1

        with self._locked_file(scope["checkpoints"], "r+", exclusive=True) as checkpoints_fh:
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
            row = self.add(
                summary,
                source=source,
                raw_resource_text=(resource_text or summary),
                user_id=user_id,
                shared=shared,
                metadata=metadata,
                reasoning_layer=reasoning_layer,
                confidence=confidence,
                memory_type=memory_type,
                happened_at=happened_at,
                decay_rate=decay_rate,
            )
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

            checkpoints = {
                "source_signatures": source_signatures,
                "source_activity": source_activity,
                "global_signatures": global_signatures,
            }
            checkpoints_fh.seek(0)
            checkpoints_fh.truncate()
            checkpoints_fh.write(self._format_checkpoints(checkpoints))
            self._flush_and_fsync(checkpoints_fh)

        curated_candidates: list[tuple[str, str]] = []
        for line in summary_lines:
            if ":" not in line:
                continue
            role, value = line.split(":", 1)
            curated_candidates.append((role.strip().lower(), value.strip()))

        facts = self._read_curated_facts_from(scope["curated"])
        by_norm = {self._normalize_memory_text(str(item["text"])): item for item in facts}
        now_iso = datetime.now(timezone.utc).isoformat()
        source_session = self._source_session_key(source)
        resolved_reasoning_layer = self._normalize_reasoning_layer(reasoning_layer)
        resolved_confidence = self._normalize_confidence(confidence, default=1.0)
        changed = False
        for role, candidate in curated_candidates:
            norm = self._normalize_memory_text(candidate)
            if not norm:
                continue
            inferred_memory_type = self._normalize_memory_type(memory_type or self._infer_memory_type(candidate, source))
            inferred_happened_at = str(happened_at or self._infer_happened_at(candidate) or "")
            inferred_decay_rate = self._normalize_decay_rate(
                decay_rate,
                default=self._default_decay_rate(
                    memory_type=inferred_memory_type,
                    category=self._categorize_memory(candidate, source),
                    happened_at=inferred_happened_at,
                ),
            )
            inferred_metadata = self._prepare_memory_metadata(
                text=candidate,
                source=source,
                metadata=metadata,
                memory_type=inferred_memory_type,
                happened_at=inferred_happened_at,
            )
            existing = by_norm.get(norm)
            if existing is None:
                facts.append(
                    {
                        "id": uuid.uuid4().hex,
                        "text": candidate,
                        "source": f"curated:{source}",
                        "created_at": now_iso,
                        "last_seen_at": now_iso,
                        "mentions": 1,
                        "session_count": 1,
                        "sessions": [source_session],
                        "importance": self._candidate_importance(
                            role=role,
                            text=candidate,
                            repeated_count=repeated_count,
                            memory_type=inferred_memory_type,
                            happened_at=inferred_happened_at,
                        ),
                        "reasoning_layer": resolved_reasoning_layer,
                        "confidence": resolved_confidence,
                        "decay_rate": inferred_decay_rate,
                        "memory_type": inferred_memory_type,
                        "happened_at": inferred_happened_at,
                        "metadata": inferred_metadata,
                    }
                )
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
                memory_type=inferred_memory_type,
                happened_at=inferred_happened_at,
            ) * 0.35
            existing["reasoning_layer"] = resolved_reasoning_layer
            existing["confidence"] = resolved_confidence
            existing["decay_rate"] = self._normalize_decay_rate(
                min(
                    self._normalize_decay_rate(existing.get("decay_rate", existing.get("decayRate", inferred_decay_rate)), default=inferred_decay_rate),
                    inferred_decay_rate,
                )
                * 0.9,
                default=inferred_decay_rate,
            )
            existing["memory_type"] = inferred_memory_type
            existing["happened_at"] = inferred_happened_at
            existing["metadata"] = self._normalize_memory_metadata(
                {
                    **self._normalize_memory_metadata(existing.get("metadata", {})),
                    **inferred_metadata,
                }
            )
            changed = True
        if changed:
            self._write_curated_facts_to(scope["curated"], facts)
        return row

    def consolidate(
        self,
        messages: Iterable[dict[str, str]],
        *,
        source: str = "session",
        user_id: str = "default",
        shared: bool = False,
        metadata: dict[str, Any] | None = None,
        reasoning_layer: str | None = None,
        confidence: float | None = None,
        memory_type: str | None = None,
        happened_at: str | None = None,
        decay_rate: float | None = None,
    ) -> MemoryRecord | None:
        clean_user = self._normalize_user_id(user_id)
        if shared or clean_user != "default":
            scope = self._scope_paths(user_id=clean_user, shared=shared)
            return self._consolidate_in_scope(
                scope,
                messages,
                source=source,
                user_id=clean_user,
                shared=shared,
                metadata=metadata,
                reasoning_layer=reasoning_layer,
                confidence=confidence,
                memory_type=memory_type,
                happened_at=happened_at,
                decay_rate=decay_rate,
            )

        lines = self._extract_consolidation_lines(messages)
        if not lines:
            return None

        source_lines: list[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", "")).strip().lower()
            content = " ".join(str(msg.get("content", "") or "").split())
            if role not in {"user", "assistant"} or not content:
                continue
            source_lines.append(f"{role}: {content}")
        resource_text = "\n".join(source_lines).strip()

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
            row = self.add(
                summary,
                source=source,
                raw_resource_text=(resource_text or summary),
                metadata=metadata,
                reasoning_layer=reasoning_layer,
                confidence=confidence,
                memory_type=memory_type,
                happened_at=happened_at,
                decay_rate=decay_rate,
            )
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
            self._flush_and_fsync(checkpoints_fh)

        curated_candidates: list[tuple[str, str]] = []
        for line in summary_lines:
            if ":" not in line:
                continue
            role, value = line.split(":", 1)
            curated_candidates.append((role.strip().lower(), value.strip()))
        self._curate_candidates(
            curated_candidates,
            source=source,
            repeated_count=repeated_count,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
        )
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

        working_rows = self.get_working_set(clean_session_id, limit=bounded_limit, include_shared_subagents=True)
        for entry in working_rows:
            snippet = str(entry.get("content", "") or "").strip()
            if not snippet or snippet in seen:
                continue
            seen.add(snippet)
            picked.append(snippet)
            if len(picked) >= bounded_limit:
                break

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

    def diagnostics(self) -> dict[str, int | str | bool]:
        return {
            "history_read_corrupt_lines": int(self._diagnostics["history_read_corrupt_lines"]),
            "history_repaired_files": int(self._diagnostics["history_repaired_files"]),
            "consolidate_writes": int(self._diagnostics["consolidate_writes"]),
            "consolidate_dedup_hits": int(self._diagnostics["consolidate_dedup_hits"]),
            "session_recovery_attempts": int(self._diagnostics["session_recovery_attempts"]),
            "session_recovery_hits": int(self._diagnostics["session_recovery_hits"]),
            "working_memory_promotions": int(self._diagnostics["working_memory_promotions"]),
            "working_memory_promotion_skips": int(self._diagnostics["working_memory_promotion_skips"]),
            "privacy_audit_writes": int(self._diagnostics["privacy_audit_writes"]),
            "privacy_audit_skipped": int(self._diagnostics["privacy_audit_skipped"]),
            "privacy_audit_errors": int(self._diagnostics["privacy_audit_errors"]),
            "privacy_ttl_deleted": int(self._diagnostics["privacy_ttl_deleted"]),
            "privacy_encrypt_events": int(self._diagnostics["privacy_encrypt_events"]),
            "privacy_encrypt_errors": int(self._diagnostics["privacy_encrypt_errors"]),
            "privacy_decrypt_events": int(self._diagnostics["privacy_decrypt_events"]),
            "privacy_decrypt_errors": int(self._diagnostics["privacy_decrypt_errors"]),
            "privacy_key_load_events": int(self._diagnostics["privacy_key_load_events"]),
            "privacy_key_create_events": int(self._diagnostics["privacy_key_create_events"]),
            "privacy_key_errors": int(self._diagnostics["privacy_key_errors"]),
            "last_error": str(self._diagnostics["last_error"]),
            "backend_name": str(self._backend_diagnostics["backend_name"]),
            "backend_supported": bool(self._backend_diagnostics["backend_supported"]),
            "backend_initialized": bool(self._backend_diagnostics["backend_initialized"]),
            "backend_init_error": str(self._backend_diagnostics["backend_init_error"]),
            "backend_driver": str(self._backend_diagnostics["backend_driver"]),
            "backend_connection_ok": bool(self._backend_diagnostics["backend_connection_ok"]),
            "backend_vector_extension": bool(self._backend_diagnostics["backend_vector_extension"]),
            "backend_vector_version": str(self._backend_diagnostics["backend_vector_version"]),
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
                "layer_deleted": 0,
                "backend_deleted": 0,
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
                "layer_deleted": 0,
                "backend_deleted": 0,
                "deleted_count": 0,
            }
        deleted = self._delete_records_by_ids(set(selected_ids))
        deleted["deleted_ids"] = selected_ids
        deleted["deleted_count"] = len(selected_ids)
        return deleted

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
                stored = asdict(parsed)
                stored["text"] = self._encrypt_text_for_category(str(parsed.text or ""), parsed.category)
                history_lines.append(json.dumps(stored, ensure_ascii=False))
        self._atomic_write_text_locked(self.history_path, ("\n".join(history_lines) + "\n") if history_lines else "")

        if self.curated_path is not None and isinstance(curated_rows, list):
            facts = []
            for row in curated_rows:
                if isinstance(row, dict):
                    facts.append(row)
            self._write_curated_facts(facts)

        if isinstance(checkpoints, dict):
            self._atomic_write_text_locked(self.checkpoints_path, self._format_checkpoints(checkpoints))

        if isinstance(profile, dict):
            merged_profile = self._default_profile()
            merged_profile.update(profile)
            self._write_json_dict(self.profile_path, merged_profile)

        if isinstance(privacy, dict):
            merged_privacy = self._default_privacy()
            merged_privacy.update(privacy)
            self._write_json_dict(self.privacy_path, merged_privacy)

    def _write_snapshot_payload(
        self,
        payload: dict[str, Any],
        *,
        tag: str = "",
        advance_branch: bool = True,
        branch_name: str = "",
    ) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_tag = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(tag or "").strip()).strip("-")
        version_id = f"{stamp}-{safe_tag}" if safe_tag else stamp
        version_path = self.versions_path / f"{version_id}.json.gz"
        with gzip.open(version_path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        if advance_branch:
            current_branch = branch_name or self._current_branch_name()
            self._advance_branch_head(current_branch, version_id)
        return version_id

    def snapshot(self, tag: str = "") -> str:
        payload = self.export_payload()
        return self._write_snapshot_payload(payload, tag=tag)

    def branch(self, name: str, from_version: str = "", checkout: bool = False) -> dict[str, Any]:
        clean_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(name or "").strip()).strip("-")
        if not clean_name:
            raise ValueError("branch name is required")
        meta = self._load_branches_metadata()
        branches = meta.get("branches", {})
        if not isinstance(branches, dict):
            branches = {}
        if clean_name in branches:
            raise ValueError(f"branch already exists: {clean_name}")

        base_version = str(from_version or "").strip() or self._current_branch_head()
        now_iso = self._utcnow_iso()
        branches[clean_name] = {
            "head": base_version,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        meta["branches"] = branches
        if checkout:
            meta["current"] = clean_name
        self._save_branches_metadata(meta)
        self._sync_branch_head_file()
        return {
            "name": clean_name,
            "head": base_version,
            "current": str(meta.get("current", "main") or "main"),
            "checkout": bool(checkout),
        }

    def branches(self) -> dict[str, Any]:
        meta = self._load_branches_metadata()
        return {
            "current": str(meta.get("current", "main") or "main"),
            "branches": meta.get("branches", {}),
        }

    def checkout_branch(self, name: str) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("branch name is required")
        self._set_current_branch(clean_name)
        return {"current": clean_name, "head": self._current_branch_head()}

    @staticmethod
    def _merge_record_lists(preferred: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in fallback:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id", "")).strip()
            if row_id:
                merged[row_id] = dict(row)
        for row in preferred:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id", "")).strip()
            if row_id:
                merged[row_id] = dict(row)
        return sorted(merged.values(), key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))))

    @staticmethod
    def _merge_profile_conservative(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        merged = dict(target)
        for key, value in source.items():
            current_value = merged.get(key)
            if key not in merged or current_value is None or current_value == "" or current_value == [] or current_value == {}:
                merged[key] = value
        source_interests = source.get("interests", [])
        target_interests = target.get("interests", [])
        if isinstance(source_interests, list) and isinstance(target_interests, list):
            merged["interests"] = sorted({str(item) for item in source_interests + target_interests if str(item).strip()})
        return merged

    @staticmethod
    def _merge_privacy_conservative(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        merged = dict(target)
        for key in ("never_memorize_patterns", "ephemeral_categories", "encrypted_categories"):
            src_list = source.get(key, [])
            tgt_list = target.get(key, [])
            if isinstance(src_list, list) and isinstance(tgt_list, list):
                merged[key] = sorted({str(item) for item in src_list + tgt_list if str(item).strip()})
        src_ttl = source.get("ephemeral_ttl_days")
        tgt_ttl = target.get("ephemeral_ttl_days")
        try:
            src_ttl_i = int(src_ttl)
        except Exception:
            src_ttl_i = 0
        try:
            tgt_ttl_i = int(tgt_ttl)
        except Exception:
            tgt_ttl_i = 0
        ttl_candidates = [val for val in (src_ttl_i, tgt_ttl_i) if val > 0]
        if ttl_candidates:
            merged["ephemeral_ttl_days"] = min(ttl_candidates)
        merged["audit_log"] = bool(source.get("audit_log", True)) and bool(target.get("audit_log", True))
        return merged

    def merge(self, source_branch: str, target_branch: str, tag: str = "merge") -> dict[str, Any]:
        meta = self._load_branches_metadata()
        branches = meta.get("branches", {})
        if not isinstance(branches, dict):
            raise ValueError("branch metadata missing")
        source_row = branches.get(source_branch)
        target_row = branches.get(target_branch)
        if not isinstance(source_row, dict) or not isinstance(target_row, dict):
            raise ValueError("source or target branch not found")

        source_head = str(source_row.get("head", "") or "")
        target_head = str(target_row.get("head", "") or "")
        if not source_head or not target_head:
            raise ValueError("source and target branches must have head versions")

        def _load(version_id: str) -> dict[str, Any]:
            version_path = self.versions_path / f"{version_id}.json.gz"
            if not version_path.exists():
                return {}
            with gzip.open(version_path, "rt", encoding="utf-8") as fh:
                payload = json.load(fh)
            return payload if isinstance(payload, dict) else {}

        source_payload = _load(source_head)
        target_payload = _load(target_head)
        merged_payload = {
            "version": 1,
            "exported_at": self._utcnow_iso(),
            "history": self._merge_record_lists(
                list(source_payload.get("history", [])) if isinstance(source_payload.get("history", []), list) else [],
                list(target_payload.get("history", [])) if isinstance(target_payload.get("history", []), list) else [],
            ),
            "curated": self._merge_record_lists(
                list(source_payload.get("curated", [])) if isinstance(source_payload.get("curated", []), list) else [],
                list(target_payload.get("curated", [])) if isinstance(target_payload.get("curated", []), list) else [],
            ),
            "checkpoints": target_payload.get("checkpoints", {}),
            "profile": self._merge_profile_conservative(
                dict(source_payload.get("profile", {})) if isinstance(source_payload.get("profile", {}), dict) else {},
                dict(target_payload.get("profile", {})) if isinstance(target_payload.get("profile", {}), dict) else {},
            ),
            "privacy": self._merge_privacy_conservative(
                dict(source_payload.get("privacy", {})) if isinstance(source_payload.get("privacy", {}), dict) else {},
                dict(target_payload.get("privacy", {})) if isinstance(target_payload.get("privacy", {}), dict) else {},
            ),
        }

        version_id = self._write_snapshot_payload(
            merged_payload,
            tag=f"{tag}-{source_branch}-into-{target_branch}",
            advance_branch=False,
        )
        meta = self._load_branches_metadata()
        branches = meta.get("branches", {})
        if not isinstance(branches, dict):
            branches = {}
        target_meta = branches.get(target_branch, {})
        if not isinstance(target_meta, dict):
            target_meta = {}
        target_meta["head"] = version_id
        target_meta["updated_at"] = self._utcnow_iso()
        if "created_at" not in target_meta:
            target_meta["created_at"] = self._utcnow_iso()
        branches[target_branch] = target_meta
        meta["branches"] = branches
        self._save_branches_metadata(meta)
        self._sync_branch_head_file()

        current_branch = str(meta.get("current", "main") or "main")
        imported = False
        if current_branch == target_branch:
            self.import_payload(merged_payload)
            imported = True
        return {
            "source": source_branch,
            "target": target_branch,
            "source_head": source_head,
            "target_head_before": target_head,
            "target_head_after": version_id,
            "version": version_id,
            "imported": imported,
        }

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
        reasoning_layers: Counter[str] = Counter()
        confidence_values: list[float] = []
        confidence_buckets: Counter[str] = Counter()

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
            reasoning_layers[self._normalize_reasoning_layer(getattr(row, "reasoning_layer", "fact"))] += 1

            confidence_value = self._normalize_confidence(getattr(row, "confidence", 1.0), default=1.0)
            if math.isfinite(confidence_value):
                confidence_values.append(confidence_value)
                bounded_confidence = max(0.0, min(1.0, confidence_value))
                if bounded_confidence < 0.4:
                    confidence_buckets["low"] += 1
                elif bounded_confidence < 0.7:
                    confidence_buckets["medium"] += 1
                elif bounded_confidence < 0.9:
                    confidence_buckets["high"] += 1
                else:
                    confidence_buckets["very_high"] += 1
            else:
                confidence_buckets["unknown"] += 1

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

        confidence_count = len(confidence_values)
        confidence_avg = round((sum(confidence_values) / confidence_count), 6) if confidence_count else 0.0
        confidence_min = round(min(confidence_values), 6) if confidence_count else 0.0
        confidence_max = round(max(confidence_values), 6) if confidence_count else 0.0

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
            "reasoning_layers": {
                name: count
                for name, count in sorted(reasoning_layers.items(), key=lambda item: (-item[1], item[0]))
            },
            "confidence": {
                "count": confidence_count,
                "average": confidence_avg,
                "minimum": confidence_min,
                "maximum": confidence_max,
                "buckets": {
                    name: count
                    for name, count in sorted(confidence_buckets.items(), key=lambda item: item[0])
                },
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

    # ── Consolidation Loop ─────────────────────────────────────────────────

    consolidation_threshold: int = 10  # min episodic records per category to trigger

    async def start_consolidation_loop(self, interval_s: float = 21600.0) -> None:
        """Start background consolidation task (idempotent, default every 6h)."""
        existing = getattr(self, "_consolidation_task", None)
        if existing and not existing.done():
            return
        self._consolidation_interval_s: float = max(60.0, float(interval_s or 21600.0))
        self._consolidation_task: asyncio.Task = asyncio.create_task(self._consolidation_loop())

    async def stop_consolidation_loop(self) -> None:
        """Cancel background consolidation task cleanly."""
        task = getattr(self, "_consolidation_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consolidation_task = None

    async def _consolidation_loop(self) -> None:
        interval = getattr(self, "_consolidation_interval_s", 21600.0)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.consolidate_categories()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._diagnostics["last_error"] = f"consolidation_loop: {exc}"

    # ── Decay GC Loop ─────────────────────────────────────────────────────────

    _DECAY_GC_THRESHOLD = 0.95  # fraction of _DECAY_MAX_PENALTY that triggers deletion

    async def start_decay_loop(self, interval_s: float = 3600.0) -> None:
        """Start background decay GC task (idempotent, default every 1h).

        Periodically scans records whose decay_rate > 0 and deletes those whose
        accumulated decay_penalty has reached _DECAY_GC_THRESHOLD × _DECAY_MAX_PENALTY,
        preventing unbounded growth of stale ephemeral records.
        """
        existing = getattr(self, "_decay_task", None)
        if existing and not existing.done():
            return
        self._decay_interval_s: float = max(60.0, float(interval_s or 3600.0))
        self._decay_task: asyncio.Task = asyncio.create_task(self._decay_loop())

    async def stop_decay_loop(self) -> None:
        """Cancel background decay GC task cleanly."""
        task = getattr(self, "_decay_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._decay_task = None

    async def _decay_loop(self) -> None:
        interval = getattr(self, "_decay_interval_s", 3600.0)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.purge_decayed_records()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._diagnostics["last_error"] = f"decay_loop: {exc}"

    async def purge_decayed_records(self) -> dict[str, int]:
        """Delete records whose decay penalty has reached the GC threshold.

        Only targets records with decay_rate > 0. Returns {purged: N}.
        """
        threshold = self._DECAY_MAX_PENALTY * self._DECAY_GC_THRESHOLD
        expired_ids: set[str] = set()

        try:
            history = await asyncio.to_thread(self._read_history_records)
        except Exception:
            history = []

        for row in history:
            if float(getattr(row, "decay_rate", 0.0) or 0.0) <= 0.0:
                continue
            if self._decay_penalty(row) >= threshold:
                row_id = str(getattr(row, "id", "") or "").strip()
                if row_id:
                    expired_ids.add(row_id)

        if not expired_ids:
            return {"purged": 0}

        try:
            deleted = await asyncio.to_thread(self._delete_records_by_ids, expired_ids)
            purged = int(deleted.get("deleted_count", 0) or 0)
        except Exception as exc:
            self._diagnostics["last_error"] = f"decay_purge: {exc}"
            purged = 0

        if purged > 0:
            self._diagnostics["decay_gc_purged"] = int(self._diagnostics.get("decay_gc_purged", 0)) + purged

        return {"purged": purged}

    async def consolidate_categories(self) -> dict[str, int]:
        """Group episodic records by category and store a summary as a knowledge record.

        For each category with >= consolidation_threshold unconsolidated event-type
        records, builds a plain-text summary and stores it as a 'knowledge' record.
        Marks source records as consolidated via metadata flag.

        Returns {category: consolidated_count}.
        """
        results: dict[str, int] = {}
        threshold = int(getattr(self, "consolidation_threshold", 10))

        backend = getattr(self, "backend", None)
        fetch = getattr(backend, "fetch_layer_records", None)
        if not callable(fetch):
            return results

        try:
            all_rows: list[dict] = await asyncio.to_thread(fetch, layer="item", limit=4000)
        except Exception as exc:
            self._diagnostics["last_error"] = f"consolidation_fetch: {exc}"
            return results

        # Group unconsolidated event records by category
        by_category: dict[str, list[dict]] = {}
        for row in all_rows:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            meta = payload.get("metadata") or {}
            if bool(meta.get("consolidated", False)):
                continue
            mem_type = str(payload.get("memory_type", "") or "").strip()
            if mem_type not in ("event", ""):
                continue
            category = str(row.get("category", "") or "context").strip()
            by_category.setdefault(category, []).append(row)

        for category, rows in by_category.items():
            if len(rows) < threshold:
                continue

            # Build summary text from record texts
            lines = []
            for row in rows:
                payload = row.get("payload", {})
                text = str(payload.get("text", "") or "").strip()
                if text:
                    lines.append(text)

            if not lines:
                continue

            summary = f"[{category}] {len(lines)} events: " + " | ".join(lines[:20])
            now = datetime.now(timezone.utc).isoformat()

            try:
                await asyncio.to_thread(
                    self.add,
                    summary,
                    source="consolidation",
                    memory_type="knowledge",
                    metadata={"consolidated_from": category, "consolidated_count": len(lines)},
                )
            except Exception as exc:
                self._diagnostics["last_error"] = f"consolidation_add: {exc}"
                continue

            # Mark source records as consolidated
            upsert = getattr(backend, "upsert_layer_record", None)
            if callable(upsert):
                for row in rows:
                    payload = row.get("payload", {})
                    if not isinstance(payload, dict):
                        continue
                    meta = dict(payload.get("metadata") or {})
                    meta["consolidated"] = True
                    meta["consolidated_at"] = now
                    updated_payload = {**payload, "metadata": meta}
                    try:
                        await asyncio.to_thread(
                            upsert,
                            layer=row.get("layer", "item"),
                            record_id=row["record_id"],
                            payload=updated_payload,
                            category=row.get("category", "context"),
                            created_at=row.get("created_at", now),
                            updated_at=now,
                        )
                    except Exception:
                        pass

            results[category] = len(lines)

        return results


# Backward-compatible API expected by legacy CLI.
def add_note(text: str) -> None:
    MemoryStore().add(text, source="legacy")


def search_notes(query: str, limit: int = 10) -> list[str]:
    return [row.text for row in MemoryStore().search(query, limit=limit)]
