from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from clawlite.core.memory_api import delete_by_prefixes, retrieve


def test_memory_api_delete_by_prefixes_respects_limit_and_dedupes_ids() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(id="abc123", created_at=(now).isoformat()),
        SimpleNamespace(id="abc123", created_at=(now).isoformat()),
        SimpleNamespace(id="abc999", created_at=(now).isoformat()),
        SimpleNamespace(id="zzz000", created_at=(now).isoformat()),
    ]
    deleted = delete_by_prefixes(
        ["abc"],
        limit=1,
        normalize_prefix=lambda value: str(value).strip().lower(),
        read_history_records=lambda: list(rows[:2]),
        curated_records=lambda: list(rows[2:]),
        record_sort_key=lambda row: (datetime.fromisoformat(row.created_at), row.id),
        match_prefixes=lambda value, prefixes: any(str(value).lower().startswith(prefix) for prefix in prefixes),
        delete_records_by_ids=lambda ids: {"history_deleted": len(ids)},
    )

    assert deleted["deleted_ids"] == ["abc999"]
    assert deleted["deleted_count"] == 1
    assert deleted["history_deleted"] == 1


def test_memory_api_retrieve_supports_rag_and_llm_fallback() -> None:
    progressive = {
        "hits": [{"id": "1"}],
        "category_hits": [{"category": "events"}],
        "resource_hits": [{"resource_id": "r1"}],
        "rewritten_query": "alpha project",
        "episodic_digest": "digest",
        "progressive": {"stage": "item"},
    }
    rag = retrieve(
        "alpha",
        limit=3,
        method="rag",
        user_id="",
        session_id="cli:1",
        include_shared=False,
        reasoning_layers=None,
        min_confidence=None,
        filters=None,
        build_progressive_retrieval_payload=lambda *args, **kwargs: dict(progressive),
        refine_hits_with_llm=lambda *args, **kwargs: None,
    )
    assert rag["method"] == "rag"
    assert rag["count"] == 1
    assert rag["rewritten_query"] == "alpha project"

    llm = retrieve(
        "alpha",
        limit=3,
        method="llm",
        user_id="",
        session_id="cli:1",
        include_shared=False,
        reasoning_layers=None,
        min_confidence=None,
        filters=None,
        build_progressive_retrieval_payload=lambda *args, **kwargs: dict(progressive),
        refine_hits_with_llm=lambda *args, **kwargs: None,
    )
    assert llm["method"] == "llm"
    assert llm["metadata"]["fallback_to_rag"] is True
    assert llm["answer"] == ""
    assert llm["next_step_query"] == ""


def test_memory_api_retrieve_rejects_invalid_method() -> None:
    with pytest.raises(ValueError):
        retrieve(
            "alpha",
            limit=3,
            method="nope",
            user_id="",
            session_id="cli:1",
            include_shared=False,
            reasoning_layers=None,
            min_confidence=None,
            filters=None,
            build_progressive_retrieval_payload=lambda *args, **kwargs: {
                "hits": [],
                "category_hits": [],
                "resource_hits": [],
                "rewritten_query": "",
                "episodic_digest": "",
                "progressive": {},
            },
            refine_hits_with_llm=lambda *args, **kwargs: None,
        )
