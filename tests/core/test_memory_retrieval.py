from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from clawlite.core.memory_retrieval import (
    build_progressive_retrieval_payload,
    collect_retrieval_records,
    curated_records,
    evaluate_retrieval_sufficiency,
    recover_session_context,
    resolve_retrieval_scopes,
    query_coverage,
    refine_hits_with_llm,
    retrieve_category_hits,
    retrieve_resource_hits,
    rewrite_retrieval_query,
)


def test_retrieve_resource_hits_reads_recent_matching_records(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    resources.mkdir(parents=True, exist_ok=True)
    resource_file = resources / "conv_20260317.jsonl"
    resource_file.write_text(
        '{"id":"rec-1","text":"secret text","source":"session:a","category":"context","created_at":"2026-03-17T00:00:00+00:00"}\n'
        '{"id":"rec-2","text":"ignored","source":"session:b","category":"events","created_at":"2026-03-17T00:01:00+00:00"}\n',
        encoding="utf-8",
    )

    hits = retrieve_resource_hits(
        scopes=[{"resources": resources}],
        record_ids=["rec-1"],
        limit=5,
        locked_file=lambda path, mode, exclusive=False: open(path, mode, encoding="utf-8"),
        decrypt_text_for_category=lambda text, category: f"{category}:{text}",
        resource_layer_value="resource",
    )

    assert hits == [
        {
            "id": "rec-1",
            "text": "context:secret text",
            "source": "session:a",
            "category": "context",
            "created_at": "2026-03-17T00:00:00+00:00",
            "layer": "resource",
        }
    ]


def test_build_progressive_retrieval_payload_adds_resource_stage_when_items_are_insufficient(tmp_path: Path) -> None:
    record = SimpleNamespace(id="row-1", text="release checklist", category="ops")

    payload = build_progressive_retrieval_payload(
        "release checklist alice",
        limit=3,
        user_id="default",
        session_id="sess-1",
        include_shared=False,
        reasoning_layers=None,
        min_confidence=None,
        filters=None,
        rewrite_retrieval_query=lambda query: f"{query} refined",
        collect_retrieval_records=lambda **kwargs: ([record], {}, {}, [{"resources": tmp_path}], False),
        retrieve_category_hits=lambda query, records, limit: [
            {"category": "ops", "sample_text": "release checklist", "score": 1.0}
        ],
        evaluate_retrieval_sufficiency=lambda query, texts, stage: {
            "stage": stage,
            "sufficient": stage == "resource",
            "missing_tokens": ["alice"] if stage != "resource" else [],
        },
        rank_records=lambda query, records, **kwargs: list(records),
        serialize_hit=lambda row: {"id": row.id, "text": row.text},
        retrieve_resource_hits=lambda **kwargs: [{"id": "row-1", "text": "owner alice", "layer": "resource"}],
        synthesize_visible_episode_digest=lambda **kwargs: {"summary": "digest"},
    )

    assert payload["rewritten_query"] == "release checklist alice refined"
    assert payload["hits"] == [{"id": "row-1", "text": "release checklist"}]
    assert payload["resource_hits"] == [{"id": "row-1", "text": "owner alice", "layer": "resource"}]
    assert [stage["stage"] for stage in payload["progressive"]["stages"]] == ["category", "item", "resource"]
    assert payload["episodic_digest"] == {"summary": "digest"}


def test_refine_hits_with_llm_parses_json_or_falls_back_to_plain_text() -> None:
    json_payload = refine_hits_with_llm(
        "project alpha",
        [{"id": "1", "text": "Project alpha deploys on Friday."}],
        run_completion=lambda prompt: {
            "choices": [
                {"message": {"content": '{"answer":"Friday","next_step_query":"rollback plan?"}'}}
            ]
        },
    )
    plain_payload = refine_hits_with_llm(
        "project alpha",
        [{"id": "1", "text": "Project alpha deploys on Friday."}],
        run_completion=lambda prompt: {
            "choices": [
                {"message": {"content": "Project alpha deploys on Friday."}}
            ]
        },
    )

    assert json_payload == {"answer": "Friday", "next_step_query": "rollback plan?"}
    assert plain_payload == {"answer": "Project alpha deploys on Friday.", "next_step_query": ""}


def test_rewrite_retrieval_query_removes_stopwords_but_keeps_entities() -> None:
    rewritten = rewrite_retrieval_query(
        "what is the release checklist for alice",
        compact_whitespace=lambda value: " ".join(str(value or "").split()),
        extract_entities=lambda text: {"people": ["alice"]} if "alice" in text.lower() else {},
        tokens=lambda text: [part.lower() for part in str(text or "").split()],
        rewrite_stopwords={"what", "is", "the", "for"},
    )

    assert rewritten == "release checklist alice"


def test_query_coverage_and_sufficiency_track_temporal_matches() -> None:
    coverage = query_coverage(
        "project alpha next week",
        ["project alpha review monday"],
        tokens=lambda text: [part.lower() for part in str(text or "").split()],
        extract_entities=lambda text: {},
        entity_match_score=lambda query_entities, memory_entities: 0.0,
        query_has_temporal_intent=lambda text: "week" in str(text or "").lower(),
        memory_has_temporal_markers=lambda text: "monday" in str(text or "").lower(),
    )
    sufficiency = evaluate_retrieval_sufficiency(
        "project alpha next week",
        ["project alpha review monday"],
        stage="resource",
        query_coverage_fn=lambda query, texts: coverage,
        tokens=lambda text: [part.lower() for part in str(text or "").split()],
        query_has_temporal_intent=lambda text: "week" in str(text or "").lower(),
    )

    assert coverage["temporal_match"] is True
    assert sufficiency["sufficient"] is True
    assert sufficiency["reason"] == "resource_temporal_match_sufficient"


def test_retrieve_category_hits_prefers_category_with_stronger_signal() -> None:
    rows = [
        SimpleNamespace(
            category="events",
            text="release checklist for alice next monday",
            memory_type="event",
            happened_at="2026-03-17T00:00:00+00:00",
            metadata={"reinforcement_count": 3},
            source="session:a",
        ),
        SimpleNamespace(
            category="ops",
            text="build pipeline status",
            memory_type="knowledge",
            happened_at="",
            metadata={},
            source="session:b",
        ),
    ]

    hits = retrieve_category_hits(
        "release checklist alice next week",
        rows,
        limit=2,
        tokens=lambda text: [part.lower() for part in str(text or "").split()],
        extract_entities=lambda text: {"people": ["alice"]} if "alice" in str(text or "").lower() else {},
        entity_match_score=lambda query_entities, memory_entities: 1.0 if query_entities == memory_entities and query_entities else 0.0,
        query_has_temporal_intent=lambda text: "week" in str(text or "").lower(),
        memory_has_temporal_markers=lambda text: "monday" in str(text or "").lower(),
        salience_boost=lambda metadata: float(metadata.get("reinforcement_count", 0) or 0),
    )

    assert hits[0]["category"] == "events"
    assert hits[0]["count"] == 1


def test_curated_records_apply_defaults_and_scope_user() -> None:
    rows = [
        {
            "id": "cur-1",
            "text": "important preference",
            "memory_type": "preference",
            "metadata": {"scope": "shared"},
        }
    ]

    records = curated_records(
        rows,
        record_cls=SimpleNamespace,
        user_id="shared",
        normalize_layer=lambda value: str(value or "item"),
        normalize_reasoning_layer=lambda value: str(value or "fact"),
        normalize_confidence=lambda value, *, default=1.0: float(value if value is not None else default),
        normalize_decay_rate=lambda value, *, default=0.0: float(value if value is not None else default),
        default_decay_rate=lambda **kwargs: 0.42,
        normalize_memory_type=lambda value: str(value or "knowledge"),
        normalize_memory_metadata=lambda value: dict(value or {}),
    )

    assert len(records) == 1
    assert records[0].user_id == "shared"
    assert records[0].source == "curated"
    assert records[0].decay_rate == 0.42
    assert records[0].memory_type == "preference"


def test_resolve_retrieval_scopes_includes_shared_only_for_opted_in_users(tmp_path: Path) -> None:
    ensured: list[Path] = []

    def _scope_paths(*, user_id: str = "default", shared: bool = False) -> dict[str, Path]:
        root = (tmp_path / "shared") if shared else (tmp_path / user_id)
        return {
            "root": root,
            "history": root / "history.jsonl",
            "curated": root / "curated.json",
        }

    scopes = resolve_retrieval_scopes(
        user_id="alice",
        include_shared=True,
        normalize_user_id=lambda value: str(value or "default"),
        shared_opt_in=lambda user_id: user_id == "alice",
        scope_paths=_scope_paths,
        ensure_scope_paths=lambda scope: ensured.append(scope["root"]),
    )

    assert [scope["root"].name for scope in scopes] == ["alice", "shared"]
    assert [path.name for path in ensured] == ["alice", "shared"]


def test_recover_session_context_prefers_working_set_before_history_and_curated() -> None:
    diagnostics: dict[str, int] = {"session_recovery_attempts": 0, "session_recovery_hits": 0}

    snippets = recover_session_context(
        "abc",
        limit=4,
        diagnostics=diagnostics,
        source_session_key=lambda value: f"session:{str(value or '').replace('session:', '')}".strip(":"),
        get_working_set=lambda session_id, **kwargs: [{"content": "working summary"}] if session_id == "abc" else [],
        read_history_records=lambda: [SimpleNamespace(source="abc", text="history context")],
        read_curated_facts=lambda: [{"text": "curated context", "sessions": ["session:abc"]}],
    )

    assert snippets == ["working summary", "history context", "curated context"]
    assert diagnostics == {"session_recovery_attempts": 1, "session_recovery_hits": 1}


def test_collect_retrieval_records_applies_filters_and_shared_scope(tmp_path: Path) -> None:
    default_scope = {"root": tmp_path / "alice", "history": tmp_path / "alice" / "history.jsonl", "curated": tmp_path / "alice" / "curated.json"}
    shared_scope = {"root": tmp_path / "shared", "history": tmp_path / "shared" / "history.jsonl", "curated": tmp_path / "shared" / "curated.json"}

    records, curated_importance, curated_mentions, scopes, semantic_enabled = collect_retrieval_records(
        user_id="alice",
        include_shared=True,
        session_id="sess-1",
        reasoning_layers=["fact"],
        min_confidence=0.7,
        filters={"categories": ["context"]},
        normalize_user_id=lambda value: str(value or "default"),
        normalize_reasoning_layers_filter=lambda values: {str(item) for item in (values or [])},
        normalize_confidence=lambda value, *, default=0.0: float(value if value is not None else default),
        normalize_retrieval_filters=lambda payload: payload or {},
        resolve_retrieval_scopes_fn=lambda **kwargs: [default_scope, shared_scope],
        shared_root=shared_scope["root"],
        read_curated_facts_from=lambda path: [
            {"id": f"{path.parent.name}-curated", "text": "context note", "category": "context", "confidence": 0.9, "mentions": 2, "importance": 1.5, "reasoning_layer": "fact"}
        ],
        read_history_records_from=lambda path: [SimpleNamespace(id=f"{path.parent.name}-history", text="context history", confidence=0.8, reasoning_layer="fact", category="context")],
        curated_records_fn=lambda rows, *, user_id: [SimpleNamespace(id=row["id"], text=row["text"], confidence=row["confidence"], reasoning_layer=row["reasoning_layer"], category=row["category"], user_id=user_id) for row in rows],
        apply_retrieval_filters=lambda rows, filters: [row for row in rows if getattr(row, "category", "") in set(filters.get("categories", []))],
        working_episode_visible_in_session=lambda row, session_id: True,
        semantic_enabled=True,
    )

    assert [scope["root"].name for scope in scopes] == ["alice", "shared"]
    assert [row.user_id for row in records if row.id.endswith("curated")] == ["alice", "shared"]
    assert curated_importance["alice-curated"] == 1.5
    assert curated_mentions["shared-curated"] == 2
    assert semantic_enabled is True
