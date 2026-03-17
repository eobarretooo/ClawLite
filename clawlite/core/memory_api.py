from __future__ import annotations

from typing import Any, Callable, Iterable


def retrieve(
    query: str,
    *,
    limit: int,
    method: str,
    user_id: str,
    session_id: str,
    include_shared: bool,
    reasoning_layers: Iterable[str] | None,
    min_confidence: float | None,
    filters: dict[str, Any] | None,
    build_progressive_retrieval_payload: Callable[..., dict[str, Any]],
    refine_hits_with_llm: Callable[..., dict[str, Any] | None],
) -> dict[str, Any]:
    clean_query = str(query or "").strip()
    if not clean_query:
        raise ValueError("query is required")
    bounded_limit = max(1, int(limit or 1))
    resolved_user = user_id or "default"
    progressive = build_progressive_retrieval_payload(
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

    llm_refinement = refine_hits_with_llm(
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


def delete_by_prefixes(
    prefixes: Iterable[str],
    *,
    limit: int | None,
    normalize_prefix: Callable[[str], str],
    read_history_records: Callable[[], list[Any]],
    curated_records: Callable[[], list[Any]],
    record_sort_key: Callable[[Any], tuple[Any, str]],
    match_prefixes: Callable[[str, set[str]], bool],
    delete_records_by_ids: Callable[[set[str]], dict[str, Any]],
) -> dict[str, Any]:
    clean_prefixes = {normalize_prefix(prefix) for prefix in prefixes if normalize_prefix(prefix)}
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
    combined = read_history_records() + curated_records()
    combined.sort(key=record_sort_key, reverse=True)

    selected_ids: list[str] = []
    seen_ids: set[str] = set()
    for row in combined:
        row_id = str(getattr(row, "id", "") or "").strip()
        if not row_id or row_id in seen_ids:
            continue
        if not match_prefixes(row_id, clean_prefixes):
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
    deleted = delete_records_by_ids(set(selected_ids))
    deleted["deleted_ids"] = selected_ids
    deleted["deleted_count"] = len(selected_ids)
    return deleted


def export_payload(
    *,
    export_memory_payload_fn: Callable[..., dict[str, Any]],
    history_rows: list[Any],
    curated_rows: list[Any],
    checkpoints_path: Any,
    parse_checkpoints: Callable[[str], list[str]],
    profile_path: Any,
    privacy_path: Any,
    load_json_dict: Callable[[Any, dict[str, Any]], dict[str, Any]],
    default_profile: Callable[[], dict[str, Any]],
    default_privacy: Callable[[], dict[str, Any]],
    utcnow_iso: Callable[[], str],
) -> dict[str, Any]:
    return export_memory_payload_fn(
        history_rows=history_rows,
        curated_rows=curated_rows,
        checkpoints_path=checkpoints_path,
        parse_checkpoints=parse_checkpoints,
        profile_path=profile_path,
        privacy_path=privacy_path,
        load_json_dict=load_json_dict,
        default_profile=default_profile,
        default_privacy=default_privacy,
        utcnow_iso=utcnow_iso,
    )


def import_payload(
    payload: dict[str, Any],
    *,
    import_memory_payload_fn: Callable[..., None],
    record_from_payload: Callable[[dict[str, Any]], Any],
    encrypt_text_for_category: Callable[[str, str], str],
    atomic_write_text_locked: Callable[[Any, str], None],
    history_path: Any,
    curated_enabled: bool,
    write_curated_facts: Callable[[list[dict[str, object]]], None],
    checkpoints_path: Any,
    format_checkpoints: Callable[[Iterable[str]], str],
    profile_path: Any,
    privacy_path: Any,
    write_json_dict: Callable[[Any, dict[str, Any]], None],
    default_profile: Callable[[], dict[str, Any]],
    default_privacy: Callable[[], dict[str, Any]],
) -> None:
    import_memory_payload_fn(
        payload=payload,
        record_from_payload=record_from_payload,
        encrypt_text_for_category=encrypt_text_for_category,
        atomic_write_text_locked=atomic_write_text_locked,
        history_path=history_path,
        curated_enabled=curated_enabled,
        write_curated_facts=write_curated_facts,
        checkpoints_path=checkpoints_path,
        format_checkpoints=format_checkpoints,
        profile_path=profile_path,
        privacy_path=privacy_path,
        write_json_dict=write_json_dict,
        default_profile=default_profile,
        default_privacy=default_privacy,
    )


def analysis_stats(
    *,
    build_memory_analysis_stats_fn: Callable[..., dict[str, Any]],
    history_rows: list[Any],
    curated_rows: list[Any],
    semantic_enabled: bool,
    parse_iso_timestamp: Callable[[str], Any],
    has_temporal_markers: Callable[[str], bool],
    normalize_reasoning_layer: Callable[[Any], str],
    normalize_confidence: Callable[[Any], float],
    read_embeddings_map: Callable[[], dict[str, Any]],
    on_embeddings_error: Callable[[Exception], None],
) -> dict[str, Any]:
    return build_memory_analysis_stats_fn(
        history_rows=history_rows,
        curated_rows=curated_rows,
        semantic_enabled=semantic_enabled,
        parse_iso_timestamp=parse_iso_timestamp,
        has_temporal_markers=has_temporal_markers,
        normalize_reasoning_layer=normalize_reasoning_layer,
        normalize_confidence=normalize_confidence,
        read_embeddings_map=read_embeddings_map,
        on_embeddings_error=on_embeddings_error,
    )


__all__ = [
    "analysis_stats",
    "delete_by_prefixes",
    "export_payload",
    "import_payload",
    "retrieve",
]
