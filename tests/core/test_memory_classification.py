from __future__ import annotations

import re
from datetime import datetime, timezone

from clawlite.core.memory_classification import (
    categorize_memory,
    entity_match_score,
    extract_entities,
    infer_happened_at,
    infer_memory_type,
    normalize_category_label,
    prepare_memory_metadata,
)


def test_normalize_category_label_maps_synonyms() -> None:
    categories = {"preferences", "relationships", "knowledge", "context", "decisions", "skills", "events", "facts"}

    assert normalize_category_label("Learning reference", memory_categories=categories) == "knowledge"
    assert normalize_category_label("travel schedule", memory_categories=categories) == "events"
    assert normalize_category_label("??", memory_categories=categories) is None


def test_extract_entities_and_match_score_use_overlap() -> None:
    entities = extract_entities(
        "Meet alice@example.com on 2026-03-17 at 14:30 https://example.com",
        entity_url_re=re.compile(r"https?://\S+"),
        entity_email_re=re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
        entity_date_re=re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        entity_time_re=re.compile(r"\b\d{1,2}:\d{2}\b"),
    )

    score = entity_match_score(
        {"emails": ["alice@example.com"], "dates": ["2026-03-17"]},
        entities,
        entity_match_weights={"emails": 0.7, "dates": 0.4},
        entity_match_max_boost=1.0,
        normalize_entity_value_fn=lambda value: str(value or "").strip().lower(),
    )

    assert entities == {
        "urls": ["https://example.com"],
        "emails": ["alice@example.com"],
        "dates": ["2026-03-17"],
        "times": ["14:30"],
    }
    assert score == 1.0


def test_infer_happened_at_and_memory_type_cover_relative_dates() -> None:
    happened_at = infer_happened_at(
        "meeting tomorrow",
        now_utc=lambda: datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc),
    )
    memory_type = infer_memory_type(
        "meeting tomorrow",
        "session:a",
        infer_happened_at_fn=lambda text: happened_at,
    )

    assert happened_at == "2026-03-18T00:00:00+00:00"
    assert memory_type == "event"


def test_prepare_memory_metadata_adds_entities_source_session_and_hash() -> None:
    metadata = prepare_memory_metadata(
        text="deploy https://example.com on 2026-03-17",
        source="session:abc",
        metadata={"priority": "high"},
        memory_type="knowledge",
        happened_at="2026-03-17T00:00:00+00:00",
        normalize_memory_metadata=lambda value: dict(value or {}),
        extract_entities_fn=lambda text: {
            "urls": ["https://example.com"],
            "dates": ["2026-03-17"],
            "emails": [],
            "times": [],
        },
        source_session_key_fn=lambda source: source.split(":", 1)[-1],
        memory_content_hash_fn=lambda text, memory_type: f"{memory_type}:hash",
    )

    assert metadata["entities"]["urls"] == ["https://example.com"]
    assert metadata["happened_at_hint"] == "2026-03-17T00:00:00+00:00"
    assert metadata["source_session"] == "abc"
    assert metadata["content_hash"] == "knowledge:hash"


def test_categorize_memory_falls_back_to_heuristic_when_llm_is_invalid() -> None:
    category = categorize_memory(
        "deadline for product launch",
        "session:a",
        memory_auto_categorize=True,
        memory_categories={"preferences", "relationships", "knowledge", "context", "decisions", "skills", "events", "facts"},
        classify_category_with_llm_fn=lambda text: "invalid",
        heuristic_category_fn=lambda text, source: "events",
    )

    assert category == "events"
