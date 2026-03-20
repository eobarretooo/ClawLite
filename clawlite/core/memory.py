from __future__ import annotations

import json
import gzip
import hashlib
import math
import os
import re
import asyncio
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

from clawlite.core.memory_backend import MemoryBackend, resolve_memory_backend
from clawlite.core.memory_artifacts import (
    append_resource_layer as _append_resource_layer_helper,
    upsert_item_layer as _upsert_item_layer_helper,
)
from clawlite.core.memory_add import (
    build_pending_record as _build_pending_record_helper,
    finalize_added_record as _finalize_added_record_helper,
)
from clawlite.core.memory_api import (
    analysis_stats as _analysis_stats_helper,
    delete_by_prefixes as _delete_by_prefixes_helper,
    export_payload as _export_payload_helper,
    import_payload as _import_payload_helper,
    retrieve as _retrieve_helper,
)
from clawlite.core.memory_classification import (
    categorize_memory as _categorize_memory_helper,
    classify_category_with_llm as _classify_category_with_llm_helper,
    entity_match_score as _entity_match_score_helper,
    extract_entities as _extract_entities_helper,
    heuristic_category as _heuristic_category_helper,
    infer_happened_at as _infer_happened_at_helper,
    infer_memory_type as _infer_memory_type_helper,
    memory_content_hash as _memory_content_hash_helper,
    normalize_category_label as _normalize_category_label_helper,
    normalize_entity_value as _normalize_entity_value_helper,
    prepare_memory_metadata as _prepare_memory_metadata_helper,
)
from clawlite.core.memory_curation import (
    candidate_importance as _candidate_importance_helper,
    consolidate_messages as _consolidate_messages_helper,
    curate_candidates as _curate_candidates_helper,
    extract_consolidation_lines as _extract_consolidation_lines_helper,
)
from clawlite.core.memory_history import (
    append_or_reinforce_history_record as _append_or_reinforce_history_record_helper,
    read_history_records as _read_history_records_helper,
    read_history_records_from as _read_history_records_from_helper,
    repair_history_file as _repair_history_file_helper,
    stored_history_payload as _stored_history_payload_helper,
    upsert_history_record_by_id as _upsert_history_record_by_id_helper,
)
from clawlite.core.memory_ingest import (
    compact_whitespace as _compact_whitespace,
    memory_text_from_file as _memory_text_from_file,
    memory_text_from_url as _memory_text_from_url,
    metadata_hint as _metadata_hint,
    try_ocr_image_text as _try_ocr_image_text,
    try_transcribe_audio_text as _try_transcribe_audio_text,
)
from clawlite.core.memory_layers import (
    load_category_items_from_path as _load_category_items_from_path,
    upsert_category_item_rows as _upsert_category_item_rows,
    write_category_items_to_path as _write_category_items_to_path,
    write_category_summary_to_path as _write_category_summary_to_path,
)
from clawlite.core.memory_maintenance import (
    consolidate_categories as _consolidate_categories,
    periodic_task_loop as _periodic_task_loop,
    purge_decayed_records as _purge_decayed_records,
    start_periodic_task as _start_periodic_task,
    stop_periodic_task as _stop_periodic_task,
)
from clawlite.core.memory_policy import (
    integration_hint as _integration_hint,
    integration_policies_snapshot as _integration_policies_snapshot,
    integration_policy as _integration_policy,
)
from clawlite.core.memory_prune import (
    cleanup_expired_ephemeral_records as _cleanup_expired_ephemeral_records_helper,
    delete_records_by_ids as _delete_records_by_ids_helper,
    delete_records_by_ids_in_scope as _delete_records_by_ids_in_scope_helper,
    prune_curated_facts_for_ids as _prune_curated_facts_for_ids_helper,
    prune_item_and_category_layers as _prune_item_and_category_layers_helper,
    prune_jsonl_records_for_ids as _prune_jsonl_records_for_ids_helper,
)
from clawlite.core.memory_privacy import (
    append_privacy_audit_event as _append_privacy_audit_event_helper,
    decrypt_text_for_category as _decrypt_text_for_category_helper,
    encrypted_prefix as _encrypted_prefix_helper,
    encrypt_text_for_category as _encrypt_text_for_category_helper,
    is_encrypted_category as _is_encrypted_category_helper,
    legacy_encrypted_prefix as _legacy_encrypted_prefix_helper,
    load_or_create_privacy_key as _load_or_create_privacy_key_helper,
    privacy_block_reason as _privacy_block_reason_helper,
    privacy_settings as _privacy_settings_helper,
    xor_with_keystream as _xor_with_keystream_helper,
)
from clawlite.core.memory_resources import (
    create_resource as _create_resource_helper,
    fetch_record_by_id as _fetch_record_by_id_helper,
    get_record_ttl as _get_record_ttl_helper,
    get_resource as _get_resource_helper,
    get_resource_records as _get_resource_records_helper,
    list_resources as _list_resources_helper,
    purge_expired_records as _purge_expired_records_helper,
    set_record_ttl as _set_record_ttl_helper,
)
from clawlite.core.memory_profile import (
    extract_timezone as _extract_timezone_helper,
    extract_topics as _extract_topics_helper,
    profile_prompt_hint as _profile_prompt_hint_helper,
    update_profile_from_record as _update_profile_from_record_helper,
    update_profile_from_text as _update_profile_from_text_helper,
    update_profile_upcoming_events as _update_profile_upcoming_events_helper,
)
from clawlite.core.memory_retrieval import (
    build_progressive_retrieval_payload as _build_progressive_retrieval_payload_helper,
    collect_retrieval_records as _collect_retrieval_records_helper,
    curated_records as _curated_records_helper,
    evaluate_retrieval_sufficiency as _evaluate_retrieval_sufficiency_helper,
    filter_records_to_categories as _filter_records_to_categories,
    list_recent_candidates as _list_recent_candidates_helper,
    query_coverage as _query_coverage_helper,
    refine_hits_with_llm as _refine_hits_with_llm_helper,
    recover_session_context as _recover_session_context_helper,
    resolve_retrieval_scopes as _resolve_retrieval_scopes_helper,
    retrieve_category_hits as _retrieve_category_hits_helper,
    retrieve_resource_hits as _retrieve_resource_hits_helper,
    rewrite_retrieval_query as _rewrite_retrieval_query_helper,
)
from clawlite.core.memory_quality import (
    merge_quality_tuning_state as _merge_quality_tuning_state,
    normalize_quality_tuning_state as _normalize_quality_tuning_state,
    quality_state_snapshot as _quality_state_snapshot,
    update_quality_state as _update_quality_state,
    update_quality_tuning_state as _update_quality_tuning_state,
)
from clawlite.core.memory_reporting import (
    build_memory_analysis_stats as _build_memory_analysis_stats,
    build_memory_diagnostics as _build_memory_diagnostics,
)
from clawlite.core.memory_search import (
    BM25Okapi,
    rank_records as _rank_records_helper,
    search_records as _search_records_helper,
)
from clawlite.core.memory_versions import (
    checkout_memory_branch as _checkout_memory_branch,
    create_memory_branch as _create_memory_branch,
    diff_memory_versions as _diff_memory_versions,
    export_memory_payload as _export_memory_payload,
    import_memory_payload as _import_memory_payload,
    list_memory_branches as _list_memory_branches,
    merge_memory_branches as _merge_memory_branches,
    rollback_memory_version as _rollback_memory_version,
    write_snapshot_payload as _write_snapshot_payload_helper,
)
from clawlite.core.memory_working_set import (
    collect_visible_working_set as _collect_visible_working_set_helper,
    default_working_memory_share_scope as _default_working_memory_share_scope_helper,
    default_working_memory_state as _default_working_memory_state_helper,
    episodic_digest_label as _episodic_digest_label_helper,
    episodic_session_boost as _episodic_session_boost_helper,
    is_working_episode_record as _is_working_episode_record_helper,
    normalize_session_id as _normalize_session_id_helper,
    normalize_user_id as _normalize_user_id_helper,
    normalize_working_memory_entry as _normalize_working_memory_entry_helper,
    normalize_working_memory_promotion_state as _normalize_working_memory_promotion_state_helper,
    normalize_working_memory_session as _normalize_working_memory_session_helper,
    normalize_working_memory_share_scope as _normalize_working_memory_share_scope_helper,
    normalize_working_memory_state_payload as _normalize_working_memory_state_payload_helper,
    parent_session_id as _parent_session_id_helper,
    promote_working_memory_locked as _promote_working_memory_locked_helper,
    remember_working_message as _remember_working_message_helper,
    synthesize_visible_episode_digest as _synthesize_visible_episode_digest_helper,
    working_episode_context as _working_episode_context_helper,
    working_episode_visible_in_session as _working_episode_visible_in_session_helper,
    working_memory_episode_summary as _working_memory_episode_summary_helper,
    working_memory_recent_direct_messages as _working_memory_recent_direct_messages_helper,
    working_memory_related_sessions as _working_memory_related_sessions_helper,
    working_memory_share_group as _working_memory_share_group_helper,
)
from clawlite.core.memory_workflows import (
    consolidate as _consolidate_workflow_helper,
    consolidate_in_scope as _consolidate_in_scope_helper,
    ingest_file as _ingest_file_helper,
    memorize as _memorize_workflow_helper,
)

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
    resource_id: str | None = None
    consolidated: bool = False


@dataclass(slots=True)
class ResourceContext:
    """Hierarchical context container — groups related memory records."""

    name: str
    kind: str = "project"  # "project" | "person" | "conversation" | "document"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: __import__("uuid").uuid4().hex)
    created_at: str = field(
        default_factory=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
    )


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
    _WORKING_MEMORY_PROMOTION_RATE_LIMIT_WINDOW_S = 3600
    _WORKING_MEMORY_PROMOTION_RATE_LIMIT_MAX = 6
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
            "working_memory_promotion_rate_limited": 0,
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
        backend_vector_index = False
        backend_vector_index_kind = ""
        backend_vector_index_error = ""

        def _capture_backend_details() -> None:
            nonlocal backend_driver, backend_connection_ok, backend_vector_extension, backend_vector_version
            nonlocal backend_vector_index, backend_vector_index_kind, backend_vector_index_error, backend_init_error
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
            backend_vector_index = bool(details.get("vector_index", False))
            backend_vector_index_kind = str(details.get("vector_index_kind", "") or "")
            backend_vector_index_error = str(details.get("vector_index_error", "") or "")
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
            "backend_vector_index": backend_vector_index,
            "backend_vector_index_kind": backend_vector_index_kind,
            "backend_vector_index_error": backend_vector_index_error,
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
        return _quality_state_snapshot(
            quality_state_path=self.quality_state_path,
            load_json_dict=self._load_json_dict,
            default_quality_state=self._default_quality_state,
            normalize_quality_tuning_state=self._normalize_quality_tuning_state,
        )

    def integration_policy(self, actor: str, *, session_id: str = "") -> dict[str, Any]:
        return _integration_policy(
            snapshot=self.quality_state_snapshot(),
            actor=actor,
            session_id=session_id,
            quality_int=self._quality_int,
        )

    def integration_policies_snapshot(self, *, session_id: str = "") -> dict[str, Any]:
        return _integration_policies_snapshot(
            session_id=session_id,
            policy_resolver=lambda actor: self.integration_policy(actor, session_id=session_id),
        )

    def integration_hint(self, actor: str, *, session_id: str = "") -> str:
        return _integration_hint(self.integration_policy(actor, session_id=session_id))

    def profile_prompt_hint(self) -> str:
        return _profile_prompt_hint_helper(
            load_json_dict=self._load_json_dict,
            profile_path=self.profile_path,
            default_profile=self._default_profile,
            parse_iso_timestamp=self._parse_iso_timestamp,
        )

    def _normalize_quality_tuning_state(self, raw: Any) -> dict[str, Any]:
        return _normalize_quality_tuning_state(
            raw=raw,
            default_quality_tuning_state=self._default_quality_tuning_state,
            quality_int=self._quality_int,
            max_recent_actions=self._MAX_QUALITY_TUNING_RECENT_ACTIONS,
        )

    def _merge_quality_tuning_state(self, current: Any, patch: Any) -> dict[str, Any]:
        return _merge_quality_tuning_state(
            current=current,
            patch=patch,
            normalize_quality_tuning_state=self._normalize_quality_tuning_state,
            quality_int=self._quality_int,
        )

    def update_quality_tuning_state(self, tuning_patch: dict[str, Any] | None = None) -> dict[str, Any]:
        return _update_quality_tuning_state(
            previous_state=self.quality_state_snapshot(),
            tuning_patch=tuning_patch,
            merge_quality_tuning_state=self._merge_quality_tuning_state,
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
            quality_state_path=self.quality_state_path,
        )

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
        return _update_quality_state(
            previous_state=self.quality_state_snapshot(),
            retrieval_metrics=retrieval_metrics,
            turn_stability_metrics=turn_stability_metrics,
            semantic_metrics=semantic_metrics,
            reasoning_layer_metrics=reasoning_layer_metrics,
            gateway_metrics=gateway_metrics,
            sampled_at=sampled_at,
            tuning_patch=tuning_patch,
            quality_int=self._quality_int,
            quality_float=self._quality_float,
            quality_reasoning_metrics_payload=self._quality_reasoning_metrics_payload,
            merge_quality_tuning_state=self._merge_quality_tuning_state,
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
            quality_state_path=self.quality_state_path,
            max_quality_history=self._MAX_QUALITY_HISTORY,
        )

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
        return _normalize_user_id_helper(user_id)

    @staticmethod
    def _normalize_session_id(session_id: str) -> str:
        return _normalize_session_id_helper(session_id)

    @classmethod
    def _parent_session_id(cls, session_id: str) -> str:
        return _parent_session_id_helper(
            session_id,
            normalize_session_id_fn=cls._normalize_session_id,
        )

    @classmethod
    def _working_memory_share_group(cls, session_id: str) -> str:
        return _working_memory_share_group_helper(
            session_id,
            normalize_session_id_fn=cls._normalize_session_id,
            parent_session_id_fn=cls._parent_session_id,
        )

    @classmethod
    def _default_working_memory_share_scope(cls, session_id: str) -> str:
        return _default_working_memory_share_scope_helper(
            session_id,
            parent_session_id_fn=cls._parent_session_id,
        )

    @classmethod
    def _normalize_working_memory_share_scope(cls, value: Any, *, session_id: str) -> str:
        return _normalize_working_memory_share_scope_helper(
            value,
            session_id=session_id,
            allowed_scopes=cls._WORKING_MEMORY_SHARE_SCOPE_SET,
            default_scope_fn=cls._default_working_memory_share_scope,
        )

    @classmethod
    def _normalize_working_memory_promotion_state(cls, value: Any) -> dict[str, Any]:
        return _normalize_working_memory_promotion_state_helper(value)

    @classmethod
    def _default_working_memory_state(cls) -> dict[str, Any]:
        del cls
        return _default_working_memory_state_helper()

    @classmethod
    def _normalize_working_memory_entry(
        cls,
        payload: Any,
        *,
        session_id: str,
        fallback_user_id: str = "default",
    ) -> dict[str, Any] | None:
        return _normalize_working_memory_entry_helper(
            payload,
            session_id=session_id,
            fallback_user_id=fallback_user_id,
            normalize_session_id_fn=cls._normalize_session_id,
            normalize_user_id_fn=cls._normalize_user_id,
            parent_session_id_fn=cls._parent_session_id,
            normalize_working_memory_share_scope_fn=lambda value, clean_session_id: cls._normalize_working_memory_share_scope(
                value,
                session_id=clean_session_id,
            ),
            normalize_memory_metadata_fn=cls._normalize_memory_metadata,
            utcnow_iso=cls._utcnow_iso,
        )

    @classmethod
    def _normalize_working_memory_session(
        cls,
        session_id: str,
        payload: Any,
    ) -> dict[str, Any] | None:
        return _normalize_working_memory_session_helper(
            session_id,
            payload,
            normalize_session_id_fn=cls._normalize_session_id,
            normalize_user_id_fn=cls._normalize_user_id,
            parent_session_id_fn=cls._parent_session_id,
            normalize_working_memory_share_scope_fn=lambda value, clean_session_id: cls._normalize_working_memory_share_scope(
                value,
                session_id=clean_session_id,
            ),
            normalize_working_memory_promotion_state_fn=cls._normalize_working_memory_promotion_state,
            normalize_working_memory_entry_fn=lambda item, clean_session_id, user_id: cls._normalize_working_memory_entry(
                item,
                session_id=clean_session_id,
                fallback_user_id=user_id,
            ),
            max_messages_per_session=cls._WORKING_MEMORY_MAX_MESSAGES_PER_SESSION,
        )

    @classmethod
    def _normalize_working_memory_state_payload(cls, payload: Any) -> dict[str, Any]:
        return _normalize_working_memory_state_payload_helper(
            payload,
            normalize_working_memory_session_fn=cls._normalize_working_memory_session,
            max_sessions=cls._WORKING_MEMORY_MAX_SESSIONS,
        )

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
        return _working_memory_related_sessions_helper(
            sessions,
            primary,
            include_shared_subagents=include_shared_subagents,
            normalize_working_memory_session_fn=cls._normalize_working_memory_session,
            normalize_working_memory_share_scope_fn=lambda value, clean_session_id: cls._normalize_working_memory_share_scope(
                value,
                session_id=clean_session_id,
            ),
        )

    @classmethod
    def _working_memory_recent_direct_messages(cls, entry: dict[str, Any]) -> list[dict[str, Any]]:
        return _working_memory_recent_direct_messages_helper(
            entry,
            normalize_working_memory_entry_fn=lambda item, clean_session_id, user_id: cls._normalize_working_memory_entry(
                item,
                session_id=clean_session_id,
                fallback_user_id=user_id,
            ),
        )

    @classmethod
    def _is_working_episode_record(cls, row: MemoryRecord) -> bool:
        return _is_working_episode_record_helper(
            row,
            normalize_memory_metadata_fn=cls._normalize_memory_metadata,
        )

    @classmethod
    def _working_episode_context(cls, row: MemoryRecord) -> dict[str, str]:
        return _working_episode_context_helper(
            row,
            normalize_memory_metadata_fn=cls._normalize_memory_metadata,
            normalize_session_id_fn=cls._normalize_session_id,
            parent_session_id_fn=cls._parent_session_id,
            working_memory_share_group_fn=cls._working_memory_share_group,
            normalize_working_memory_share_scope_fn=lambda value, clean_session_id: cls._normalize_working_memory_share_scope(
                value,
                session_id=clean_session_id,
            ),
        )

    @classmethod
    def _working_episode_visible_in_session(cls, row: MemoryRecord, *, session_id: str) -> bool:
        return _working_episode_visible_in_session_helper(
            row,
            session_id=session_id,
            normalize_session_id_fn=cls._normalize_session_id,
            is_working_episode_record_fn=cls._is_working_episode_record,
            working_episode_context_fn=cls._working_episode_context,
            parent_session_id_fn=cls._parent_session_id,
            working_memory_share_group_fn=cls._working_memory_share_group,
        )

    @classmethod
    def _episodic_session_boost(cls, row: MemoryRecord, *, session_id: str) -> float:
        return _episodic_session_boost_helper(
            row,
            session_id=session_id,
            normalize_session_id_fn=cls._normalize_session_id,
            is_working_episode_record_fn=cls._is_working_episode_record,
            working_episode_context_fn=cls._working_episode_context,
            working_episode_visible_in_session_fn=lambda current_row, clean_session_id: cls._working_episode_visible_in_session(
                current_row,
                session_id=clean_session_id,
            ),
            parent_session_id_fn=cls._parent_session_id,
        )

    @classmethod
    def _episodic_digest_label(cls, *, active_session_id: str, target_session_id: str) -> str:
        return _episodic_digest_label_helper(
            active_session_id=active_session_id,
            target_session_id=target_session_id,
            normalize_session_id_fn=cls._normalize_session_id,
            parent_session_id_fn=cls._parent_session_id,
        )

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
        return _synthesize_visible_episode_digest_helper(
            query=query,
            session_id=session_id,
            records=records,
            curated_importance=curated_importance,
            curated_mentions=curated_mentions,
            semantic_enabled=semantic_enabled,
            limit=limit,
            normalize_session_id_fn=self._normalize_session_id,
            is_working_episode_record_fn=self._is_working_episode_record,
            rank_records_fn=self._rank_records,
            working_episode_context_fn=self._working_episode_context,
            episodic_digest_label_fn=lambda active_session_id, target_session_id: self._episodic_digest_label(
                active_session_id=active_session_id,
                target_session_id=target_session_id,
            ),
            compact_whitespace_fn=self._compact_whitespace,
        )

    @classmethod
    def _working_memory_episode_summary(cls, session_id: str, messages: list[dict[str, Any]]) -> str:
        return _working_memory_episode_summary_helper(
            session_id,
            messages,
            promotion_window=cls._WORKING_MEMORY_PROMOTION_WINDOW,
            normalize_session_id_fn=cls._normalize_session_id,
            extract_topics_fn=cls._extract_topics,
            compact_whitespace_fn=cls._compact_whitespace,
        )

    def _promote_working_memory_locked(
        self,
        *,
        sessions: dict[str, dict[str, Any]],
        session_id: str,
        force: bool,
    ) -> MemoryRecord | None:
        return _promote_working_memory_locked_helper(
            sessions=sessions,
            session_id=session_id,
            force=force,
            diagnostics=self._diagnostics,
            normalize_working_memory_session_fn=self._normalize_working_memory_session,
            working_memory_recent_direct_messages_fn=self._working_memory_recent_direct_messages,
            extract_consolidation_lines_fn=self._extract_consolidation_lines,
            compact_whitespace_fn=self._compact_whitespace,
            normalize_working_memory_promotion_state_fn=self._normalize_working_memory_promotion_state,
            chunk_signature_fn=self._chunk_signature,
            working_memory_episode_summary_fn=self._working_memory_episode_summary,
            normalize_memory_metadata_fn=self._normalize_memory_metadata,
            add_record_fn=self.add,
            utcnow_iso=self._utcnow_iso,
            parse_iso_fn=self._parse_iso_timestamp,
            promotion_min_messages=self._WORKING_MEMORY_PROMOTION_MIN_MESSAGES,
            promotion_window=self._WORKING_MEMORY_PROMOTION_WINDOW,
            promotion_step=self._WORKING_MEMORY_PROMOTION_STEP,
            promotion_rate_limit_window_s=self._WORKING_MEMORY_PROMOTION_RATE_LIMIT_WINDOW_S,
            promotion_rate_limit_max=self._WORKING_MEMORY_PROMOTION_RATE_LIMIT_MAX,
        )

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
            _remember_working_message_helper(
                sessions=sessions,
                session_id=clean_session_id,
                role=role,
                content=clean_content,
                user_id=user_id,
                metadata=metadata,
                allow_promotion=allow_promotion,
                normalize_working_memory_session_fn=self._normalize_working_memory_session,
                normalize_user_id_fn=self._normalize_user_id,
                working_memory_share_group_fn=self._working_memory_share_group,
                default_working_memory_share_scope_fn=self._default_working_memory_share_scope,
                parent_session_id_fn=self._parent_session_id,
                normalize_working_memory_promotion_state_fn=self._normalize_working_memory_promotion_state,
                normalize_working_memory_entry_fn=lambda payload, current_session_id, fallback_user_id: self._normalize_working_memory_entry(
                    payload,
                    session_id=current_session_id,
                    fallback_user_id=fallback_user_id,
                ),
                normalize_memory_metadata_fn=self._normalize_memory_metadata,
                utcnow_iso=self._utcnow_iso,
                max_messages_per_session=self._WORKING_MEMORY_MAX_MESSAGES_PER_SESSION,
                promote_working_memory_locked_fn=self._promote_working_memory_locked,
            )
            state["sessions"] = sessions
            state["updated_at"] = self._utcnow_iso()
            normalized_state = self._normalize_working_memory_state_payload(state)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(normalized_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            self._flush_and_fsync(fh)

    def remember_working_messages(
        self,
        session_id: str,
        *,
        messages: Iterable[dict[str, Any]],
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
        allow_promotion: bool = True,
    ) -> None:
        clean_session_id = self._normalize_session_id(session_id)
        if not clean_session_id:
            return

        pending_messages: list[dict[str, Any]] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "") or "").strip().lower() or "user"
            content = " ".join(str(item.get("content", "") or "").split())
            if not content:
                continue
            pending_messages.append(
                {
                    "role": role,
                    "content": content,
                    "user_id": str(item.get("user_id", user_id) or user_id),
                    "metadata": item.get("metadata", metadata),
                }
            )
        if not pending_messages:
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
            for item in pending_messages:
                _remember_working_message_helper(
                    sessions=sessions,
                    session_id=clean_session_id,
                    role=str(item.get("role", "") or ""),
                    content=str(item.get("content", "") or ""),
                    user_id=str(item.get("user_id", user_id) or user_id),
                    metadata=item.get("metadata", metadata),
                    allow_promotion=allow_promotion,
                    normalize_working_memory_session_fn=self._normalize_working_memory_session,
                    normalize_user_id_fn=self._normalize_user_id,
                    working_memory_share_group_fn=self._working_memory_share_group,
                    default_working_memory_share_scope_fn=self._default_working_memory_share_scope,
                    parent_session_id_fn=self._parent_session_id,
                    normalize_working_memory_promotion_state_fn=self._normalize_working_memory_promotion_state,
                    normalize_working_memory_entry_fn=lambda payload, current_session_id, fallback_user_id: self._normalize_working_memory_entry(
                        payload,
                        session_id=current_session_id,
                        fallback_user_id=fallback_user_id,
                    ),
                    normalize_memory_metadata_fn=self._normalize_memory_metadata,
                    utcnow_iso=self._utcnow_iso,
                    max_messages_per_session=self._WORKING_MEMORY_MAX_MESSAGES_PER_SESSION,
                    promote_working_memory_locked_fn=self._promote_working_memory_locked,
                )
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
        return _collect_visible_working_set_helper(
            session_id,
            limit=limit,
            include_shared_subagents=include_shared_subagents,
            load_working_memory_state_fn=self._load_working_memory_state,
            normalize_session_id_fn=self._normalize_session_id,
            normalize_working_memory_session_fn=self._normalize_working_memory_session,
            working_memory_related_sessions_fn=self._working_memory_related_sessions,
            normalize_working_memory_entry_fn=lambda payload, current_session_id, fallback_user_id: self._normalize_working_memory_entry(
                payload,
                session_id=current_session_id,
                fallback_user_id=fallback_user_id,
            ),
        )

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
        return _privacy_settings_helper(
            load_json_dict=self._load_json_dict,
            privacy_path=self.privacy_path,
            default_privacy=self._default_privacy,
        )

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
        _append_privacy_audit_event_helper(
            action=action,
            reason=reason,
            source=source,
            category=category,
            record_id=record_id,
            metadata=metadata,
            diagnostics=self._diagnostics,
            privacy_settings_loader=self._privacy_settings,
            utcnow_iso=self._utcnow_iso,
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
            privacy_audit_path=self.privacy_audit_path,
        )

    @staticmethod
    def _encrypted_prefix() -> str:
        return _encrypted_prefix_helper()

    @staticmethod
    def _legacy_encrypted_prefix() -> str:
        return _legacy_encrypted_prefix_helper()

    @staticmethod
    def _xor_with_keystream(data: bytes, *, key: bytes, nonce: bytes) -> bytes:
        return _xor_with_keystream_helper(data, key=key, nonce=nonce)

    def _load_or_create_privacy_key(self) -> bytes | None:
        key = _load_or_create_privacy_key_helper(
            cached_key=self._privacy_key,
            privacy_key_path=self.privacy_key_path,
            diagnostics=self._diagnostics,
        )
        if isinstance(key, (bytes, bytearray)) and len(key) == 32:
            self._privacy_key = bytes(key)
            return bytes(key)
        return None

    def _is_encrypted_category(self, category: str, *, settings: dict[str, Any] | None = None) -> bool:
        return _is_encrypted_category_helper(
            category,
            settings=settings,
            privacy_settings_loader=self._privacy_settings,
        )

    def _encrypt_text_for_category(self, text: str, category: str, *, settings: dict[str, Any] | None = None) -> str:
        return _encrypt_text_for_category_helper(
            text,
            category,
            settings=settings,
            privacy_settings_loader=self._privacy_settings,
            load_or_create_privacy_key_fn=self._load_or_create_privacy_key,
            xor_with_keystream_fn=self._xor_with_keystream,
            diagnostics=self._diagnostics,
        )

    def _decrypt_text_for_category(self, text: str, category: str, *, settings: dict[str, Any] | None = None) -> str:
        return _decrypt_text_for_category_helper(
            text,
            category,
            settings=settings,
            load_or_create_privacy_key_fn=self._load_or_create_privacy_key,
            xor_with_keystream_fn=self._xor_with_keystream,
            diagnostics=self._diagnostics,
        )

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
        removed = _prune_jsonl_records_for_ids_helper(
            path=self.embeddings_path,
            record_ids=removed_ids,
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
        )
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
        return _classify_category_with_llm_helper(
            text,
            run_coro_sync=self._run_coro_sync,
            normalize_category_label=self._normalize_category_label,
        )

    @classmethod
    def _normalize_category_label(cls, raw_label: str) -> str | None:
        return _normalize_category_label_helper(raw_label, memory_categories=cls._MEMORY_CATEGORIES)

    @classmethod
    def _extract_entities(cls, text: str) -> dict[str, list[str]]:
        return _extract_entities_helper(
            text,
            entity_url_re=cls._ENTITY_URL_RE,
            entity_email_re=cls._ENTITY_EMAIL_RE,
            entity_date_re=cls._ENTITY_DATE_RE,
            entity_time_re=cls._ENTITY_TIME_RE,
        )

    @staticmethod
    def _normalize_entity_value(value: str) -> str:
        return _normalize_entity_value_helper(value)

    @classmethod
    def _entity_match_score(
        cls,
        query_entities: dict[str, list[str]],
        memory_entities: dict[str, list[str]],
    ) -> float:
        return _entity_match_score_helper(
            query_entities,
            memory_entities,
            entity_match_weights=cls._ENTITY_MATCH_WEIGHTS,
            entity_match_max_boost=cls._ENTITY_MATCH_MAX_BOOST,
            normalize_entity_value_fn=cls._normalize_entity_value,
        )

    def _heuristic_category(self, text: str, source: str) -> str:
        return _heuristic_category_helper(
            text,
            source,
            extract_entities_fn=self._extract_entities,
        )

    def _categorize_memory(self, text: str, source: str) -> str:
        return _categorize_memory_helper(
            text,
            source,
            memory_auto_categorize=self.memory_auto_categorize,
            memory_categories=self._MEMORY_CATEGORIES,
            classify_category_with_llm_fn=self._classify_category_with_llm,
            heuristic_category_fn=self._heuristic_category,
        )

    @staticmethod
    def _memory_content_hash(text: str, memory_type: str) -> str:
        return _memory_content_hash_helper(text, memory_type)

    def _infer_memory_type(self, text: str, source: str, *, category: str = "") -> str:
        return _infer_memory_type_helper(
            text,
            source,
            category=category,
            infer_happened_at_fn=self._infer_happened_at,
        )

    @classmethod
    def _infer_happened_at(cls, text: str) -> str:
        return _infer_happened_at_helper(
            text,
            now_utc=lambda: datetime.now(timezone.utc),
        )

    def _prepare_memory_metadata(
        self,
        *,
        text: str,
        source: str,
        metadata: dict[str, Any] | None,
        memory_type: str,
        happened_at: str,
    ) -> dict[str, Any]:
        return _prepare_memory_metadata_helper(
            text=text,
            source=source,
            metadata=metadata,
            memory_type=memory_type,
            happened_at=happened_at,
            normalize_memory_metadata=self._normalize_memory_metadata,
            extract_entities_fn=self._extract_entities,
            source_session_key_fn=self._source_session_key,
            memory_content_hash_fn=self._memory_content_hash,
        )

    @classmethod
    def _record_temporal_anchor(cls, row: MemoryRecord) -> str:
        happened_at = str(getattr(row, "happened_at", "") or "").strip()
        if happened_at and cls._parse_iso_timestamp(happened_at).year > 1:
            return happened_at
        return str(row.created_at or "")

    @staticmethod
    def _metadata_hint(metadata: dict[str, Any] | None) -> str:
        return _metadata_hint(metadata)

    @staticmethod
    def _compact_whitespace(value: str) -> str:
        return _compact_whitespace(value)

    @classmethod
    def _try_ocr_image_text(cls, target: Path) -> str:
        return _try_ocr_image_text(target)

    @classmethod
    def _try_transcribe_audio_text(cls, target: Path) -> str:
        return _try_transcribe_audio_text(target)

    @classmethod
    def _memory_text_from_file(
        cls,
        file_path: str,
        *,
        modality: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        return _memory_text_from_file(
            file_path,
            modality=modality,
            metadata=metadata,
            text_like_suffixes=cls._TEXT_LIKE_SUFFIXES,
        )

    @classmethod
    def _memory_text_from_url(
        cls,
        url: str,
        *,
        modality: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        return _memory_text_from_url(url, modality=modality, metadata=metadata)

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
        return _extract_timezone_helper(text)

    @classmethod
    def _extract_topics(cls, text: str) -> list[str]:
        return _extract_topics_helper(
            text,
            tokens=cls._tokens,
            profile_topic_stopwords=PROFILE_TOPIC_STOPWORDS,
        )

    def _privacy_block_reason(self, text: str) -> str | None:
        return _privacy_block_reason_helper(
            text,
            privacy_settings_loader=self._privacy_settings,
        )

    def _privacy_allows_memorize(self, text: str) -> bool:
        return self._privacy_block_reason(text) is None

    def _update_profile_from_text(self, text: str) -> None:
        _update_profile_from_text_helper(
            text,
            load_json_dict=self._load_json_dict,
            write_json_dict=self._write_json_dict,
            profile_path=self.profile_path,
            default_profile=self._default_profile,
            extract_timezone_fn=self._extract_timezone,
            extract_topics_fn=self._extract_topics,
            detect_emotional_tone=self._detect_emotional_tone,
            utcnow_iso=self._utcnow_iso,
        )

    def _update_profile_upcoming_events(self, record: MemoryRecord) -> None:
        _update_profile_upcoming_events_helper(
            record,
            normalize_memory_type=self._normalize_memory_type,
            parse_iso_timestamp=self._parse_iso_timestamp,
            load_json_dict=self._load_json_dict,
            write_json_dict=self._write_json_dict,
            profile_path=self.profile_path,
            default_profile=self._default_profile,
            metadata_content_hash=self._metadata_content_hash,
            compact_whitespace=self._compact_whitespace,
            utcnow_iso=self._utcnow_iso,
        )

    def _update_profile_from_record(self, record: MemoryRecord) -> None:
        _update_profile_from_record_helper(
            record,
            normalize_memory_metadata=self._normalize_memory_metadata,
            update_profile_from_text_fn=self._update_profile_from_text,
            update_profile_upcoming_events_fn=self._update_profile_upcoming_events,
        )

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
        return _read_history_records_from_helper(
            history_path=history_path,
            locked_file=self._locked_file,
            record_from_payload=self._record_from_payload,
            decrypt_text_for_category=self._decrypt_text_for_category,
        )

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
        return _candidate_importance_helper(
            role=role,
            text=text,
            repeated_count=repeated_count,
            memory_type=memory_type,
            happened_at=happened_at,
            normalize_memory_type=cls._normalize_memory_type,
            parse_iso_timestamp=cls._parse_iso_timestamp,
        )

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
        read_curated_facts: Callable[[], list[dict[str, object]]] | None = None,
        write_curated_facts: Callable[[list[dict[str, object]]], None] | None = None,
    ) -> None:
        if self.curated_path is None and read_curated_facts is None:
            return
        _curate_candidates_helper(
            candidates,
            source=source,
            repeated_count=repeated_count,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
            read_curated_facts=read_curated_facts or self._read_curated_facts,
            write_curated_facts=write_curated_facts or self._write_curated_facts,
            normalize_memory_text=self._normalize_memory_text,
            source_session_key=self._source_session_key,
            normalize_reasoning_layer=self._normalize_reasoning_layer,
            normalize_confidence=lambda value: self._normalize_confidence(value, default=1.0),
            normalize_memory_type=self._normalize_memory_type,
            infer_memory_type=self._infer_memory_type,
            infer_happened_at=self._infer_happened_at,
            normalize_decay_rate=self._normalize_decay_rate,
            default_decay_rate=self._default_decay_rate,
            categorize_memory=self._categorize_memory,
            prepare_memory_metadata=self._prepare_memory_metadata,
            candidate_importance_fn=self._candidate_importance,
            normalize_memory_metadata=self._normalize_memory_metadata,
            max_curated_sessions_per_fact=self._MAX_CURATED_SESSIONS_PER_FACT,
            utcnow_iso=self._utcnow_iso,
        )

    def _extract_consolidation_lines(self, messages: Iterable[dict[str, str]]) -> list[str]:
        return _extract_consolidation_lines_helper(
            messages,
            is_curation_candidate=self._is_curation_candidate,
        )

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
        _append_resource_layer_helper(
            record=record,
            raw_text=raw_text,
            resource_layer_value=MemoryLayer.RESOURCE.value,
            encrypt_text_for_category=self._encrypt_text_for_category,
            normalize_reasoning_layer=self._normalize_reasoning_layer,
            normalize_confidence=lambda value: self._normalize_confidence(value, default=1.0),
            resource_file_for_timestamp=self._resource_file_path_for_timestamp,
            ensure_file=lambda path: self._ensure_file(path, default=""),
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
            backend_upsert_layer_record=self.backend.upsert_layer_record,
        )

    def _load_category_items(self, category: str) -> list[dict[str, Any]]:
        return _load_category_items_from_path(
            item_path=self._item_file_path(category),
            category=category,
            decrypt_text_for_category=self._decrypt_text_for_category,
        )

    def _write_category_items(self, category: str, rows: list[dict[str, Any]]) -> None:
        _write_category_items_to_path(
            item_path=self._item_file_path(category),
            category=category,
            rows=rows,
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
        )

    def _update_category_summary_file(self, category: str) -> None:
        _write_category_summary_to_path(
            category_path=self._category_file_path(category),
            category=category,
            rows=self._load_category_items(category),
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
        )

    def _stored_history_payload(self, record: MemoryRecord) -> dict[str, Any]:
        return _stored_history_payload_helper(
            record=record,
            encrypt_text_for_category=self._encrypt_text_for_category,
        )

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
        return _append_or_reinforce_history_record_helper(
            history_path=history_path,
            record=record,
            content_hash=content_hash,
            scope_key=scope_key,
            source=source,
            reinforced_at=reinforced_at,
            ensure_file=lambda path: self._ensure_file(path, default=""),
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
            record_from_payload=self._record_from_payload,
            decrypt_text_for_category=self._decrypt_text_for_category,
            record_content_hash=self._record_content_hash,
            record_scope_key=self._record_scope_key,
            reinforce_record=self._reinforce_record,
            stored_history_payload_fn=self._stored_history_payload,
        )

    def _upsert_history_record_by_id(self, history_path: Path, record: MemoryRecord, *, append_if_missing: bool = False) -> bool:
        return _upsert_history_record_by_id_helper(
            history_path=history_path,
            record=record,
            append_if_missing=append_if_missing,
            ensure_file=lambda path: self._ensure_file(path, default=""),
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
            stored_history_payload_fn=self._stored_history_payload,
        )

    def _upsert_item_layer(self, record: MemoryRecord) -> None:
        _upsert_item_layer_helper(
            record=record,
            load_category_items=self._load_category_items,
            serialize_hit=self._serialize_hit,
            encrypt_text_for_category=self._encrypt_text_for_category,
            write_category_items=self._write_category_items,
            update_category_summary=self._update_category_summary_file,
            category_file_path=self._category_file_path,
            utcnow_iso=self._utcnow_iso,
            backend_upsert_layer_record=self.backend.upsert_layer_record,
            item_layer_value=MemoryLayer.ITEM.value,
            category_layer_value=MemoryLayer.CATEGORY.value,
        )

    def _persist_layer_artifacts(self, record: MemoryRecord, *, raw_resource_text: str) -> None:
        self._append_resource_layer(record=record, raw_text=raw_resource_text)
        self._upsert_item_layer(record)

    def _load_scope_category_items(self, scope: dict[str, Path], category: str) -> list[dict[str, Any]]:
        return _load_category_items_from_path(
            item_path=self._scope_item_file_path(scope, category),
            category=category,
            decrypt_text_for_category=self._decrypt_text_for_category,
        )

    def _write_scope_category_items(self, scope: dict[str, Path], category: str, rows: list[dict[str, Any]]) -> None:
        _write_category_items_to_path(
            item_path=self._scope_item_file_path(scope, category),
            category=category,
            rows=rows,
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
        )

    def _update_scope_category_summary_file(self, scope: dict[str, Path], category: str) -> None:
        _write_category_summary_to_path(
            category_path=self._scope_category_file_path(scope, category),
            category=category,
            rows=self._load_scope_category_items(scope, category),
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
        )

    def _upsert_item_layer_in_scope(self, scope: dict[str, Path], record: MemoryRecord) -> None:
        _upsert_item_layer_helper(
            record=record,
            load_category_items=lambda category: self._load_scope_category_items(scope, category),
            serialize_hit=self._serialize_hit,
            encrypt_text_for_category=self._encrypt_text_for_category,
            write_category_items=lambda category, rows: self._write_scope_category_items(scope, category, rows),
            update_category_summary=lambda category: self._update_scope_category_summary_file(scope, category),
            category_file_path=lambda category: self._scope_category_file_path(scope, category),
            utcnow_iso=self._utcnow_iso,
            backend_upsert_layer_record=None,
            item_layer_value=MemoryLayer.ITEM.value,
            category_layer_value=MemoryLayer.CATEGORY.value,
        )

    def _persist_layer_artifacts_to_scope(self, scope: dict[str, Path], record: MemoryRecord, *, raw_resource_text: str) -> None:
        _append_resource_layer_helper(
            record=record,
            raw_text=raw_resource_text,
            resource_layer_value=MemoryLayer.RESOURCE.value,
            encrypt_text_for_category=self._encrypt_text_for_category,
            normalize_reasoning_layer=self._normalize_reasoning_layer,
            normalize_confidence=lambda value: self._normalize_confidence(value, default=1.0),
            resource_file_for_timestamp=lambda stamp: self._scope_resource_file_path_for_timestamp(scope, stamp),
            ensure_file=lambda path: self._ensure_file(path, default=""),
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
            backend_upsert_layer_record=None,
        )
        self._upsert_item_layer_in_scope(scope, record)

    def _prune_item_and_category_layers(self, record_ids: set[str]) -> int:
        return _prune_item_and_category_layers_helper(
            items_path=self.items_path,
            record_ids=record_ids,
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
            update_category_summary=self._update_category_summary_file,
        )

    def _prune_resource_layer_for_ids(self, record_ids: set[str]) -> int:
        if not record_ids:
            return 0
        deleted = 0
        for resource_file in self.resources_path.glob("conv_*.jsonl"):
            try:
                deleted += _prune_jsonl_records_for_ids_helper(
                    path=resource_file,
                    record_ids=record_ids,
                    locked_file=self._locked_file,
                    flush_and_fsync=self._flush_and_fsync,
                )
            except Exception:
                continue
        return deleted

    def _prune_history_records_for_ids(self, history_path: Path, record_ids: set[str]) -> int:
        return _prune_jsonl_records_for_ids_helper(
            path=history_path,
            record_ids=record_ids,
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
        )

    def _prune_curated_facts_for_ids(self, curated_path: Path | None, record_ids: set[str]) -> int:
        return _prune_curated_facts_for_ids_helper(
            curated_path=curated_path,
            record_ids=record_ids,
            read_curated_facts_from=self._read_curated_facts_from,
            write_curated_facts_to=self._write_curated_facts_to,
        )

    def _prune_item_and_category_layers_in_scope(self, scope: dict[str, Path], record_ids: set[str]) -> int:
        return _prune_item_and_category_layers_helper(
            items_path=scope["items"],
            record_ids=record_ids,
            utcnow_iso=self._utcnow_iso,
            atomic_write_text_locked=self._atomic_write_text_locked,
            update_category_summary=lambda category: self._update_scope_category_summary_file(scope, category),
        )

    def _prune_resource_layer_for_ids_in_scope(self, scope: dict[str, Path], record_ids: set[str]) -> int:
        if not record_ids or not scope["resources"].exists():
            return 0
        deleted = 0
        for resource_file in scope["resources"].glob("conv_*.jsonl"):
            try:
                deleted += _prune_jsonl_records_for_ids_helper(
                    path=resource_file,
                    record_ids=record_ids,
                    locked_file=self._locked_file,
                    flush_and_fsync=self._flush_and_fsync,
                )
            except Exception:
                continue
        return deleted

    def _delete_records_by_ids_in_scope(self, scope: dict[str, Path], record_ids: set[str]) -> dict[str, int]:
        return _delete_records_by_ids_in_scope_helper(
            scope=scope,
            record_ids=record_ids,
            memory_home=self.memory_home,
            prune_history_records=self._prune_history_records_for_ids,
            prune_curated_facts=self._prune_curated_facts_for_ids,
            prune_root_item_layers=self._prune_item_and_category_layers,
            prune_root_resource_layers=self._prune_resource_layer_for_ids,
            prune_scope_item_layers=self._prune_item_and_category_layers_in_scope,
            prune_scope_resource_layers=self._prune_resource_layer_for_ids_in_scope,
        )

    def _delete_records_by_ids(self, record_ids: set[str]) -> dict[str, int | list[str]]:
        return _delete_records_by_ids_helper(
            record_ids=record_ids,
            iter_existing_scopes=self._iter_existing_scopes,
            delete_records_by_ids_in_scope_fn=self._delete_records_by_ids_in_scope,
            prune_embeddings_for_ids=self._prune_embeddings_for_ids,
            backend_delete_layer_records=self.backend.delete_layer_records,
            diagnostics=self._diagnostics,
        )

    def _cleanup_expired_ephemeral_records(self) -> int:
        return _cleanup_expired_ephemeral_records_helper(
            privacy_settings=self._privacy_settings,
            iter_existing_scopes=self._iter_existing_scopes,
            read_history_records_from=self._read_history_records_from,
            read_curated_facts_from=self._read_curated_facts_from,
            parse_iso_timestamp=self._parse_iso_timestamp,
            delete_records_by_ids=self._delete_records_by_ids,
            diagnostics=self._diagnostics,
            append_privacy_audit_event=self._append_privacy_audit_event,
        )

    # ------------------------------------------------------------------
    # ResourceContext CRUD
    # ------------------------------------------------------------------

    def create_resource(self, resource: "ResourceContext") -> str:
        return _create_resource_helper(
            backend=self.backend,
            resource=resource,
        )

    def get_resource(self, resource_id: str) -> "ResourceContext | None":
        return _get_resource_helper(
            backend=self.backend,
            resource_id=resource_id,
            resource_context_cls=ResourceContext,
        )

    def list_resources(self) -> list["ResourceContext"]:
        return _list_resources_helper(
            backend=self.backend,
            resource_context_cls=ResourceContext,
        )

    def delete_resource(self, resource_id: str) -> None:
        self.backend.delete_resource(resource_id)

    def get_resource_records(self, resource_id: str) -> list["MemoryRecord"]:
        return _get_resource_records_helper(
            backend=self.backend,
            resource_id=resource_id,
            fetch_record_by_id_fn=self._fetch_record_by_id,
        )

    def _fetch_record_by_id(self, record_id: str) -> "MemoryRecord | None":
        return _fetch_record_by_id_helper(
            backend=self.backend,
            record_id=record_id,
            item_layer_value=MemoryLayer.ITEM.value,
            memory_record_cls=MemoryRecord,
        )

    # ------------------------------------------------------------------
    # TTL
    # ------------------------------------------------------------------

    def set_record_ttl(self, record_id: str, ttl_seconds: float) -> None:
        _set_record_ttl_helper(
            backend=self.backend,
            record_id=record_id,
            ttl_seconds=ttl_seconds,
        )

    def get_record_ttl(self, record_id: str) -> dict[str, str] | None:
        return _get_record_ttl_helper(
            backend=self.backend,
            record_id=record_id,
        )

    def purge_expired_records(self) -> int:
        return _purge_expired_records_helper(backend=self.backend)

    # ------------------------------------------------------------------
    # Multi-modal file ingest
    # ------------------------------------------------------------------

    def ingest_file(
        self,
        path: str,
        *,
        source: str = "file",
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        return _ingest_file_helper(
            path=path,
            source=source,
            resource_id=resource_id,
            add_record=self.add,
        )

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
        resource_id: str | None = None,
    ) -> MemoryRecord:
        row, content_hash, scope_key, reinforced_at, raw_text, scoped = _build_pending_record_helper(
            text=text,
            source=source,
            raw_resource_text=raw_resource_text,
            user_id=user_id,
            shared=shared,
            modality=modality,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
            normalize_user_id=self._normalize_user_id,
            categorize_memory=self._categorize_memory,
            normalize_memory_type=self._normalize_memory_type,
            infer_memory_type=self._infer_memory_type,
            infer_happened_at=self._infer_happened_at,
            normalize_decay_rate=self._normalize_decay_rate,
            default_decay_rate=self._default_decay_rate,
            memory_scope_key=self._memory_scope_key,
            prepare_memory_metadata=self._prepare_memory_metadata,
            seed_reinforcement_metadata=self._seed_reinforcement_metadata,
            normalize_reasoning_layer=self._normalize_reasoning_layer,
            normalize_confidence=self._normalize_confidence,
            detect_emotional_tone=self._detect_emotional_tone,
            emotional_tracking=self.emotional_tracking,
            memory_record_cls=MemoryRecord,
            metadata_content_hash=self._metadata_content_hash,
            memory_content_hash=self._memory_content_hash,
        )

        if scoped:
            clean_user = str(row.user_id or "default")
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

        return _finalize_added_record_helper(
            row=row,
            created_new=created_new,
            clean_text=str(row.text or ""),
            resource_id=resource_id,
            diagnostics=self._diagnostics,
            generate_embedding=self._generate_embedding,
            append_embedding=self._append_embedding,
            update_profile_from_record=self._update_profile_from_record,
            prune_history=self._prune_history,
            link_record_resource=self.backend.link_record_resource,
        )

    def _read_history_records(self) -> list[MemoryRecord]:
        return _read_history_records_helper(
            history_path=self.history_path,
            locked_file=self._locked_file,
            record_from_payload=self._record_from_payload,
            decrypt_text_for_category=self._decrypt_text_for_category,
            repair_history_file_fn=self._repair_history_file,
            diagnostics=self._diagnostics,
        )

    def _repair_history_file(self, valid_lines: list[str]) -> None:
        _repair_history_file_helper(
            history_path=self.history_path,
            valid_lines=valid_lines,
            atomic_write_text_locked=self._atomic_write_text_locked,
            diagnostics=self._diagnostics,
        )

    def all(self) -> list[MemoryRecord]:
        return self._read_history_records()

    def curated(self) -> list[MemoryRecord]:
        return _curated_records_helper(
            self._read_curated_facts(),
            record_cls=MemoryRecord,
            user_id="default",
            normalize_layer=self._normalize_layer,
            normalize_reasoning_layer=self._normalize_reasoning_layer,
            normalize_confidence=self._normalize_confidence,
            normalize_decay_rate=self._normalize_decay_rate,
            default_decay_rate=self._default_decay_rate,
            normalize_memory_type=self._normalize_memory_type,
            normalize_memory_metadata=self._normalize_memory_metadata,
        )

    def list_recent_candidates(
        self,
        *,
        source: str = "",
        ref_prefix: str = "",
        limit: int = 10,
        max_scan: int = 500,
    ) -> list[MemoryRecord]:
        return _list_recent_candidates_helper(
            source=source,
            ref_prefix=ref_prefix,
            limit=limit,
            max_scan=max_scan,
            fetch_layer_records=self.backend.fetch_layer_records,
            record_from_payload=self._record_from_payload,
            decrypt_text_for_category=self._decrypt_text_for_category,
            normalize_prefix=self._normalize_prefix,
            record_sort_key=self._record_sort_key,
            history_path=self.history_path,
            locked_file=self._locked_file,
            read_curated_facts=self._read_curated_facts,
            item_layer_value=MemoryLayer.ITEM.value,
        )

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
        return await _memorize_workflow_helper(
            text=text,
            messages=messages,
            source=source,
            user_id=user_id,
            shared=shared,
            include_shared=include_shared,
            file_path=file_path,
            url=url,
            modality=modality,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
            cleanup_expired_ephemeral_records=self._cleanup_expired_ephemeral_records,
            diagnostics=self._diagnostics,
            privacy_block_reason=self._privacy_block_reason,
            append_privacy_audit_event=self._append_privacy_audit_event,
            consolidate_fn=self.consolidate,
            add_fn=self.add,
            memory_text_from_file=self._memory_text_from_file,
            memory_text_from_url=self._memory_text_from_url,
        )

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
        return _resolve_retrieval_scopes_helper(
            user_id=user_id,
            include_shared=include_shared,
            normalize_user_id=self._normalize_user_id,
            shared_opt_in=self.shared_opt_in,
            scope_paths=self._scope_paths,
            ensure_scope_paths=self._ensure_scope_paths,
        )

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
        return _collect_retrieval_records_helper(
            user_id=user_id,
            include_shared=include_shared,
            session_id=session_id,
            reasoning_layers=reasoning_layers,
            min_confidence=min_confidence,
            filters=filters,
            normalize_user_id=self._normalize_user_id,
            normalize_reasoning_layers_filter=self._normalize_reasoning_layers_filter,
            normalize_confidence=self._normalize_confidence,
            normalize_retrieval_filters=self._normalize_retrieval_filters,
            resolve_retrieval_scopes_fn=self._resolve_retrieval_scopes,
            shared_root=self.shared_path,
            read_curated_facts_from=self._read_curated_facts_from,
            read_history_records_from=self._read_history_records_from,
            curated_records_fn=lambda rows, *, user_id: _curated_records_helper(
                rows,
                record_cls=MemoryRecord,
                user_id=user_id,
                normalize_layer=self._normalize_layer,
                normalize_reasoning_layer=self._normalize_reasoning_layer,
                normalize_confidence=self._normalize_confidence,
                normalize_decay_rate=self._normalize_decay_rate,
                default_decay_rate=self._default_decay_rate,
                normalize_memory_type=self._normalize_memory_type,
                normalize_memory_metadata=self._normalize_memory_metadata,
            ),
            apply_retrieval_filters=self._apply_retrieval_filters,
            working_episode_visible_in_session=self._working_episode_visible_in_session,
            semantic_enabled=self.semantic_enabled,
        )

    @classmethod
    def _rewrite_retrieval_query(cls, query: str) -> str:
        return _rewrite_retrieval_query_helper(
            query,
            compact_whitespace=cls._compact_whitespace,
            extract_entities=cls._extract_entities,
            tokens=cls._tokens,
            rewrite_stopwords=cls._RETRIEVAL_REWRITE_STOPWORDS,
        )

    @classmethod
    def _query_coverage(cls, query: str, texts: list[str]) -> dict[str, Any]:
        return _query_coverage_helper(
            query,
            texts,
            tokens=cls._tokens,
            extract_entities=cls._extract_entities,
            entity_match_score=cls._entity_match_score,
            query_has_temporal_intent=cls._query_has_temporal_intent,
            memory_has_temporal_markers=cls._memory_has_temporal_markers,
        )

    def _evaluate_retrieval_sufficiency(self, query: str, texts: list[str], *, stage: str) -> dict[str, Any]:
        return _evaluate_retrieval_sufficiency_helper(
            query,
            texts,
            stage=stage,
            query_coverage_fn=self._query_coverage,
            tokens=self._tokens,
            query_has_temporal_intent=self._query_has_temporal_intent,
        )

    def _retrieve_category_hits(self, query: str, records: list[MemoryRecord], *, limit: int) -> list[dict[str, Any]]:
        return _retrieve_category_hits_helper(
            query,
            records,
            limit=limit,
            tokens=self._tokens,
            extract_entities=self._extract_entities,
            entity_match_score=self._entity_match_score,
            query_has_temporal_intent=self._query_has_temporal_intent,
            memory_has_temporal_markers=self._memory_has_temporal_markers,
            salience_boost=self._salience_boost,
        )

    @staticmethod
    def _filter_records_to_categories(records: list[MemoryRecord], categories: list[str]) -> list[MemoryRecord]:
        return _filter_records_to_categories(records, categories)

    def _retrieve_resource_hits(
        self,
        scopes: list[dict[str, Path]],
        *,
        record_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        return _retrieve_resource_hits_helper(
            scopes=scopes,
            record_ids=record_ids,
            limit=limit,
            locked_file=self._locked_file,
            decrypt_text_for_category=self._decrypt_text_for_category,
            resource_layer_value=MemoryLayer.RESOURCE.value,
        )

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
        return _build_progressive_retrieval_payload_helper(
            query,
            limit=limit,
            user_id=user_id,
            session_id=session_id,
            include_shared=include_shared,
            reasoning_layers=reasoning_layers,
            min_confidence=min_confidence,
            filters=filters,
            rewrite_retrieval_query=self._rewrite_retrieval_query,
            collect_retrieval_records=self._collect_retrieval_records,
            retrieve_category_hits=self._retrieve_category_hits,
            evaluate_retrieval_sufficiency=self._evaluate_retrieval_sufficiency,
            rank_records=self._rank_records,
            serialize_hit=self._serialize_hit,
            retrieve_resource_hits=self._retrieve_resource_hits,
            synthesize_visible_episode_digest=self._synthesize_visible_episode_digest,
        )

    def _refine_hits_with_llm(
        self,
        query: str,
        hits: list[dict[str, Any]],
        *,
        category_hits: list[dict[str, Any]] | None = None,
        resource_hits: list[dict[str, Any]] | None = None,
    ) -> dict[str, str] | None:
        try:
            import litellm  # type: ignore
        except Exception:
            return None
        return _refine_hits_with_llm_helper(
            query,
            hits,
            category_hits=category_hits,
            resource_hits=resource_hits,
            run_completion=lambda prompt: self._run_coro_sync(
                litellm.acompletion(
                    model="gemini/gemini-2.5-flash",
                    temperature=0,
                    max_tokens=256,
                    messages=[
                        {"role": "system", "content": "Responda apenas com base na memoria fornecida."},
                        {"role": "user", "content": prompt},
                    ],
                )
            ),
        )

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
        return await asyncio.to_thread(
            _retrieve_helper,
            query,
            limit=limit,
            method=method,
            user_id=user_id,
            session_id=session_id,
            include_shared=include_shared,
            reasoning_layers=reasoning_layers,
            min_confidence=min_confidence,
            filters=filters,
            build_progressive_retrieval_payload=self._build_progressive_retrieval_payload,
            refine_hits_with_llm=self._refine_hits_with_llm,
        )

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
        return _rank_records_helper(
            query,
            records,
            curated_importance=curated_importance,
            curated_mentions=curated_mentions,
            limit=limit,
            semantic_enabled=semantic_enabled,
            session_id=session_id,
            tokens=self._tokens,
            extract_entities=self._extract_entities,
            reasoning_intent_boosts=self._reasoning_intent_boosts,
            query_has_temporal_intent=self._query_has_temporal_intent,
            generate_embedding=self._generate_embedding,
            query_similar_embeddings=lambda query_embedding, search_records: self.backend.query_similar_embeddings(
                query_embedding,
                record_ids=[row.id for row in search_records if str(row.id or "").strip()],
                limit=max(1, len(search_records)),
            ),
            read_embeddings_map=self._read_embeddings_map,
            cosine_similarity=self._cosine_similarity,
            entity_match_score=self._entity_match_score,
            recency_score=self._recency_score,
            record_temporal_anchor=self._record_temporal_anchor,
            memory_has_temporal_markers=self._memory_has_temporal_markers,
            bounded_confidence_score=self._bounded_confidence_score,
            normalize_reasoning_layer=self._normalize_reasoning_layer,
            decay_penalty=self._decay_penalty,
            upcoming_event_boost=self._upcoming_event_boost,
            salience_boost=self._salience_boost,
            episodic_session_boost=lambda row: self._episodic_session_boost(row, session_id=session_id),
            semantic_bm25_weight=self._SEMANTIC_BM25_WEIGHT,
            semantic_vector_weight=self._SEMANTIC_VECTOR_WEIGHT,
            ranking_confidence_boost_max=self._RANKING_CONFIDENCE_BOOST_MAX,
            temporal_intent_match_boost=self._TEMPORAL_INTENT_MATCH_BOOST,
            temporal_intent_miss_penalty=self._TEMPORAL_INTENT_MISS_PENALTY,
            bm25_class=BM25Okapi,
        )

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
        return _search_records_helper(
            query,
            limit=limit,
            user_id=user_id,
            session_id=session_id,
            include_shared=include_shared,
            reasoning_layers=reasoning_layers,
            min_confidence=min_confidence,
            filters=filters,
            normalize_user_id=self._normalize_user_id,
            collect_retrieval_records=self._collect_retrieval_records,
            rank_records_fn=self._rank_records,
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
        return _consolidate_in_scope_helper(
            scope=scope,
            messages=messages,
            source=source,
            user_id=user_id,
            shared=shared,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
            ensure_scope_paths=self._ensure_scope_paths,
            consolidate_messages=self._consolidate_messages,
            read_curated_facts_from=self._read_curated_facts_from,
            write_curated_facts_to=self._write_curated_facts_to,
            add_record=self.add,
        )

    def _consolidate_messages(
        self,
        messages: Iterable[dict[str, str]],
        *,
        source: str,
        metadata: dict[str, Any] | None,
        reasoning_layer: str | None,
        confidence: float | None,
        memory_type: str | None,
        happened_at: str | None,
        decay_rate: float | None,
        checkpoints_path: Path,
        add_record: Callable[[str, str], MemoryRecord],
        read_curated_facts: Callable[[], list[dict[str, object]]],
        write_curated_facts: Callable[[list[dict[str, object]]], None],
        max_checkpoint_sources: int | None = None,
        max_checkpoint_signatures: int | None = None,
    ) -> MemoryRecord | None:
        return _consolidate_messages_helper(
            messages,
            source=source,
            checkpoints_path=checkpoints_path,
            extract_consolidation_lines=self._extract_consolidation_lines,
            chunk_signature=self._chunk_signature,
            parse_checkpoints=self._parse_checkpoints,
            format_checkpoints=self._format_checkpoints,
            locked_file=self._locked_file,
            flush_and_fsync=self._flush_and_fsync,
            utcnow_iso=self._utcnow_iso,
            add_record=add_record,
            diagnostics=self._diagnostics,
            curate_candidates_fn=lambda candidates, repeated_count: self._curate_candidates(
                candidates,
                source=source,
                repeated_count=repeated_count,
                metadata=metadata,
                reasoning_layer=reasoning_layer,
                confidence=confidence,
                memory_type=memory_type,
                happened_at=happened_at,
                decay_rate=decay_rate,
                read_curated_facts=read_curated_facts,
                write_curated_facts=write_curated_facts,
            ),
            max_checkpoint_sources=max_checkpoint_sources,
            max_checkpoint_signatures=max_checkpoint_signatures,
        )

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
        return _consolidate_workflow_helper(
            messages=messages,
            source=source,
            user_id=user_id,
            shared=shared,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
            normalize_user_id=self._normalize_user_id,
            scope_paths=self._scope_paths,
            consolidate_in_scope_fn=self._consolidate_in_scope,
            consolidate_messages=self._consolidate_messages,
            checkpoints_path=self.checkpoints_path,
            read_curated_facts=self._read_curated_facts,
            write_curated_facts=self._write_curated_facts,
            add_record=self.add,
            max_checkpoint_sources=self._MAX_CHECKPOINT_SOURCES,
            max_checkpoint_signatures=self._MAX_CHECKPOINT_SIGNATURES,
        )

    def recover_session_context(self, session_id: str, *, limit: int = 4) -> list[str]:
        return _recover_session_context_helper(
            session_id,
            limit=limit,
            diagnostics=self._diagnostics,
            source_session_key=self._source_session_key,
            get_working_set=self.get_working_set,
            read_history_records=self._read_history_records,
            read_curated_facts=self._read_curated_facts,
        )

    def diagnostics(self) -> dict[str, int | str | bool]:
        return _build_memory_diagnostics(
            diagnostics=self._diagnostics,
            backend_diagnostics=self._backend_diagnostics,
        )

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
        return _delete_by_prefixes_helper(
            prefixes,
            limit=limit,
            normalize_prefix=self._normalize_prefix,
            read_history_records=self._read_history_records,
            curated_records=self.curated,
            record_sort_key=self._record_sort_key,
            match_prefixes=self._match_prefixes,
            delete_records_by_ids=self._delete_records_by_ids,
        )

    def export_payload(self) -> dict[str, Any]:
        return _export_payload_helper(
            export_memory_payload_fn=_export_memory_payload,
            history_rows=self.all(),
            curated_rows=self.curated(),
            checkpoints_path=self.checkpoints_path,
            parse_checkpoints=self._parse_checkpoints,
            profile_path=self.profile_path,
            privacy_path=self.privacy_path,
            load_json_dict=self._load_json_dict,
            default_profile=self._default_profile,
            default_privacy=self._default_privacy,
            utcnow_iso=self._utcnow_iso,
        )

    def import_payload(self, payload: dict[str, Any]) -> None:
        _import_payload_helper(
            payload,
            import_memory_payload_fn=_import_memory_payload,
            record_from_payload=self._record_from_payload,
            encrypt_text_for_category=self._encrypt_text_for_category,
            atomic_write_text_locked=self._atomic_write_text_locked,
            history_path=self.history_path,
            curated_enabled=self.curated_path is not None,
            write_curated_facts=self._write_curated_facts,
            checkpoints_path=self.checkpoints_path,
            format_checkpoints=self._format_checkpoints,
            profile_path=self.profile_path,
            privacy_path=self.privacy_path,
            write_json_dict=self._write_json_dict,
            default_profile=self._default_profile,
            default_privacy=self._default_privacy,
        )

    def _write_snapshot_payload(
        self,
        payload: dict[str, Any],
        *,
        tag: str = "",
        advance_branch: bool = True,
        branch_name: str = "",
    ) -> str:
        return _write_snapshot_payload_helper(
            payload=payload,
            versions_path=self.versions_path,
            tag=tag,
            advance_branch=advance_branch,
            branch_name=branch_name,
            current_branch_name=self._current_branch_name,
            advance_branch_head=self._advance_branch_head,
        )

    def snapshot(self, tag: str = "") -> str:
        payload = self.export_payload()
        return self._write_snapshot_payload(payload, tag=tag)

    def branch(self, name: str, from_version: str = "", checkout: bool = False) -> dict[str, Any]:
        return _create_memory_branch(
            name=name,
            from_version=from_version,
            checkout=checkout,
            load_branches_metadata=self._load_branches_metadata,
            save_branches_metadata=self._save_branches_metadata,
            sync_branch_head_file=self._sync_branch_head_file,
            current_branch_head=self._current_branch_head,
            utcnow_iso=self._utcnow_iso,
        )

    def branches(self) -> dict[str, Any]:
        return _list_memory_branches(load_branches_metadata=self._load_branches_metadata)

    def checkout_branch(self, name: str) -> dict[str, Any]:
        return _checkout_memory_branch(
            name=name,
            set_current_branch=self._set_current_branch,
            current_branch_head=self._current_branch_head,
        )

    def merge(self, source_branch: str, target_branch: str, tag: str = "merge") -> dict[str, Any]:
        return _merge_memory_branches(
            source_branch=source_branch,
            target_branch=target_branch,
            tag=tag,
            load_branches_metadata=self._load_branches_metadata,
            save_branches_metadata=self._save_branches_metadata,
            sync_branch_head_file=self._sync_branch_head_file,
            versions_path=self.versions_path,
            utcnow_iso=self._utcnow_iso,
            write_snapshot_payload=self._write_snapshot_payload,
            import_payload=self.import_payload,
        )

    def rollback(self, version_id: str) -> None:
        _rollback_memory_version(
            version_id=version_id,
            versions_path=self.versions_path,
            import_payload=self.import_payload,
        )

    def diff(self, version_a: str, version_b: str) -> dict[str, Any]:
        return _diff_memory_versions(
            versions_path=self.versions_path,
            version_a=version_a,
            version_b=version_b,
        )

    def analysis_stats(self) -> dict[str, Any]:
        def _on_embeddings_error(exc: Exception) -> None:
            self._diagnostics["last_error"] = str(exc)

        return _analysis_stats_helper(
            build_memory_analysis_stats_fn=_build_memory_analysis_stats,
            history_rows=self.all(),
            curated_rows=self.curated(),
            semantic_enabled=self.semantic_enabled,
            parse_iso_timestamp=self._parse_iso_timestamp,
            has_temporal_markers=self._memory_has_temporal_markers,
            normalize_reasoning_layer=self._normalize_reasoning_layer,
            normalize_confidence=lambda value: self._normalize_confidence(value, default=1.0),
            read_embeddings_map=self._read_embeddings_map,
            on_embeddings_error=_on_embeddings_error,
        )

    # ── Consolidation Loop ─────────────────────────────────────────────────

    consolidation_threshold: int = 10  # min episodic records per category to trigger

    async def start_consolidation_loop(self, interval_s: float = 21600.0) -> None:
        """Start background consolidation task (idempotent, default every 6h)."""
        await _start_periodic_task(
            owner=self,
            task_attr="_consolidation_task",
            interval_attr="_consolidation_interval_s",
            interval_s=interval_s,
            default_interval_s=21600.0,
            loop_factory=self._consolidation_loop,
        )

    async def stop_consolidation_loop(self) -> None:
        """Cancel background consolidation task cleanly."""
        await _stop_periodic_task(owner=self, task_attr="_consolidation_task")

    async def _consolidation_loop(self) -> None:
        await _periodic_task_loop(
            interval_s=getattr(self, "_consolidation_interval_s", 21600.0),
            work=self.consolidate_categories,
            diagnostics=self._diagnostics,
            error_prefix="consolidation_loop",
        )

    # ── Decay GC Loop ─────────────────────────────────────────────────────────

    _DECAY_GC_THRESHOLD = 0.95  # fraction of _DECAY_MAX_PENALTY that triggers deletion

    async def start_decay_loop(self, interval_s: float = 3600.0) -> None:
        """Start background decay GC task (idempotent, default every 1h).

        Periodically scans records whose decay_rate > 0 and deletes those whose
        accumulated decay_penalty has reached _DECAY_GC_THRESHOLD × _DECAY_MAX_PENALTY,
        preventing unbounded growth of stale ephemeral records.
        """
        await _start_periodic_task(
            owner=self,
            task_attr="_decay_task",
            interval_attr="_decay_interval_s",
            interval_s=interval_s,
            default_interval_s=3600.0,
            loop_factory=self._decay_loop,
        )

    async def stop_decay_loop(self) -> None:
        """Cancel background decay GC task cleanly."""
        await _stop_periodic_task(owner=self, task_attr="_decay_task")

    async def _decay_loop(self) -> None:
        await _periodic_task_loop(
            interval_s=getattr(self, "_decay_interval_s", 3600.0),
            work=self.purge_decayed_records,
            diagnostics=self._diagnostics,
            error_prefix="decay_loop",
        )

    async def purge_decayed_records(self) -> dict[str, int]:
        """Delete records whose decay penalty has reached the GC threshold.

        Only targets records with decay_rate > 0. Returns {purged: N}.
        """
        return await _purge_decayed_records(
            read_history_records=self._read_history_records,
            decay_penalty=self._decay_penalty,
            delete_records_by_ids=self._delete_records_by_ids,
            diagnostics=self._diagnostics,
            threshold=self._DECAY_MAX_PENALTY * self._DECAY_GC_THRESHOLD,
        )

    async def consolidate_categories(self) -> dict[str, int]:
        """Group episodic records by category and store a summary as a knowledge record.

        For each category with >= consolidation_threshold unconsolidated event-type
        records, builds a plain-text summary and stores it as a 'knowledge' record.
        Marks source records as consolidated via metadata flag.

        Returns {category: consolidated_count}.
        """
        return await _consolidate_categories(
            backend=getattr(self, "backend", None),
            threshold=int(getattr(self, "consolidation_threshold", 10)),
            add_record=self.add,
            diagnostics=self._diagnostics,
        )

    async def compact(self) -> dict[str, Any]:
        """Run safe maintenance passes that reduce memory bloat without deleting core history."""

        expired_records = int(self.purge_expired_records() or 0)
        decayed_payload = await self.purge_decayed_records()
        consolidated_payload = await self.consolidate_categories()
        consolidated_counts = (
            dict(consolidated_payload) if isinstance(consolidated_payload, dict) else {}
        )
        consolidated_total = 0
        for value in consolidated_counts.values():
            try:
                consolidated_total += int(value or 0)
            except Exception:
                continue
        return {
            "expired_records": expired_records,
            "decayed_records": int(
                decayed_payload.get("purged", 0) if isinstance(decayed_payload, dict) else 0
            ),
            "consolidated_records": consolidated_total,
            "consolidated_categories": consolidated_counts,
        }


# Backward-compatible API expected by legacy CLI.
def add_note(text: str) -> None:
    MemoryStore().add(text, source="legacy")


def search_notes(query: str, limit: int = 10) -> list[str]:
    return [row.text for row in MemoryStore().search(query, limit=limit)]
