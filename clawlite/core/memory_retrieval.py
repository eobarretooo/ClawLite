from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable


def filter_records_to_categories(records: list[Any], categories: list[str]) -> list[Any]:
    allowed = {str(item or "").strip().lower() for item in categories if str(item or "").strip()}
    if not allowed:
        return list(records)
    return [row for row in records if str(getattr(row, "category", "context") or "context").strip().lower() in allowed]


def rewrite_retrieval_query(
    query: str,
    *,
    compact_whitespace: Callable[[str], str],
    extract_entities: Callable[[str], dict[str, list[str]]],
    tokens: Callable[[str], list[str]],
    rewrite_stopwords: Iterable[str],
) -> str:
    raw = compact_whitespace(query)
    if not raw:
        return ""
    query_entities = extract_entities(raw)
    query_tokens = tokens(raw)
    if not query_tokens:
        return raw

    stopwords = {str(item or "").strip().lower() for item in rewrite_stopwords if str(item or "").strip()}
    preserved = [token for token in query_tokens if token not in stopwords]
    rewritten = " ".join(preserved).strip() if preserved else raw

    for values in query_entities.values():
        for value in values:
            clean_value = compact_whitespace(value)
            if clean_value and clean_value.lower() not in rewritten.lower():
                rewritten = f"{rewritten} {clean_value}".strip()

    if not rewritten:
        return raw
    if len(rewritten) + 8 < len(raw):
        return rewritten
    return raw


def query_coverage(
    query: str,
    texts: list[str],
    *,
    tokens: Callable[[str], list[str]],
    extract_entities: Callable[[str], dict[str, list[str]]],
    entity_match_score: Callable[[dict[str, list[str]], dict[str, list[str]]], float],
    query_has_temporal_intent: Callable[[str], bool],
    memory_has_temporal_markers: Callable[[str], bool],
) -> dict[str, Any]:
    query_tokens = set(tokens(query))
    if not query_tokens:
        return {
            "covered_tokens": [],
            "missing_tokens": [],
            "coverage_ratio": 0.0,
            "entity_score": 0.0,
            "temporal_match": False,
        }

    covered: set[str] = set()
    best_entity_score = 0.0
    temporal_match = False
    query_entities = extract_entities(query)
    temporal_query = query_has_temporal_intent(query)

    for text in texts:
        covered.update(query_tokens.intersection(tokens(text)))
        best_entity_score = max(best_entity_score, entity_match_score(query_entities, extract_entities(text)))
        if temporal_query and memory_has_temporal_markers(text):
            temporal_match = True

    coverage_ratio = float(len(covered)) / float(len(query_tokens)) if query_tokens else 0.0
    missing_tokens = sorted(query_tokens.difference(covered))
    return {
        "covered_tokens": sorted(covered),
        "missing_tokens": missing_tokens,
        "coverage_ratio": round(max(0.0, min(1.0, coverage_ratio)), 6),
        "entity_score": round(max(0.0, best_entity_score), 6),
        "temporal_match": temporal_match,
    }


def evaluate_retrieval_sufficiency(
    query: str,
    texts: list[str],
    *,
    stage: str,
    query_coverage_fn: Callable[[str, list[str]], dict[str, Any]],
    tokens: Callable[[str], list[str]],
    query_has_temporal_intent: Callable[[str], bool],
) -> dict[str, Any]:
    if stage == "category":
        has_signal = bool(texts)
        return {
            "stage": stage,
            "sufficient": False,
            "reason": "need_item_level_recall" if has_signal else "no_category_signal",
            "covered_tokens": [],
            "missing_tokens": sorted(set(tokens(query))),
            "coverage_ratio": 0.0,
            "entity_score": 0.0,
            "temporal_match": False,
        }

    coverage = query_coverage_fn(query, texts)
    coverage_ratio = float(coverage["coverage_ratio"])
    entity_score = float(coverage["entity_score"])
    temporal_match = bool(coverage["temporal_match"])
    temporal_query = query_has_temporal_intent(query)
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


def retrieve_category_hits(
    query: str,
    records: list[Any],
    *,
    limit: int,
    tokens: Callable[[str], list[str]],
    extract_entities: Callable[[str], dict[str, list[str]]],
    entity_match_score: Callable[[dict[str, list[str]], dict[str, list[str]]], float],
    query_has_temporal_intent: Callable[[str], bool],
    memory_has_temporal_markers: Callable[[str], bool],
    salience_boost: Callable[[dict[str, Any] | None], float],
) -> list[dict[str, Any]]:
    query_tokens = set(tokens(query))
    query_entities = extract_entities(query)
    temporal_query = query_has_temporal_intent(query)
    by_category: dict[str, dict[str, Any]] = {}

    for row in records:
        category = str(getattr(row, "category", "context") or "context")
        text = str(getattr(row, "text", "") or "")
        text_tokens = set(tokens(text))
        overlap = len(query_tokens.intersection(text_tokens))
        entity_score = entity_match_score(query_entities, extract_entities(text))
        category_overlap = len(query_tokens.intersection(tokens(category))) * 0.35
        type_overlap = len(query_tokens.intersection(tokens(str(getattr(row, "memory_type", "knowledge") or "knowledge")))) * 0.25
        temporal_bonus = 0.15 if temporal_query and (getattr(row, "happened_at", "") or memory_has_temporal_markers(text)) else 0.0
        salience_bonus = salience_boost(getattr(row, "metadata", {})) * 0.5
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
        bucket["memory_types"].add(str(getattr(row, "memory_type", "knowledge") or "knowledge"))
        bucket["sources"].add(str(getattr(row, "source", "unknown") or "unknown"))
        if score >= float(bucket["top_score"]):
            bucket["top_score"] = score
            bucket["sample_text"] = text.strip()[:160]

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


def retrieve_resource_hits(
    *,
    scopes: list[dict[str, Path]],
    record_ids: list[str],
    limit: int,
    locked_file: Callable[[Path, str], Any],
    decrypt_text_for_category: Callable[[str, str], str],
    resource_layer_value: str,
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
                with locked_file(resource_file, "r", exclusive=False) as fh:
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
                text = decrypt_text_for_category(str(payload.get("text", "") or ""), category)
                out.append(
                    {
                        "id": row_id,
                        "text": text,
                        "source": str(payload.get("source", "") or ""),
                        "category": category,
                        "created_at": str(payload.get("created_at", "") or ""),
                        "layer": resource_layer_value,
                    }
                )
                seen_ids.add(row_id)
                if len(out) >= limit:
                    return out
    return out


def build_progressive_retrieval_payload(
    query: str,
    *,
    limit: int,
    user_id: str,
    session_id: str,
    include_shared: bool,
    reasoning_layers: Iterable[str] | None,
    min_confidence: float | None,
    filters: dict[str, Any] | None,
    rewrite_retrieval_query: Callable[[str], str],
    collect_retrieval_records: Callable[..., tuple[list[Any], dict[str, float], dict[str, int], list[dict[str, Path]], bool]],
    retrieve_category_hits: Callable[[str, list[Any], int], list[dict[str, Any]]],
    evaluate_retrieval_sufficiency: Callable[[str, list[str], str], dict[str, Any]],
    rank_records: Callable[..., list[Any]],
    serialize_hit: Callable[[Any], dict[str, Any]],
    retrieve_resource_hits: Callable[..., list[dict[str, Any]]],
    synthesize_visible_episode_digest: Callable[..., dict[str, Any] | None],
) -> dict[str, Any]:
    rewritten_query = rewrite_retrieval_query(query)
    active_query = rewritten_query or query
    records, curated_importance, curated_mentions, scopes, semantic_enabled = collect_retrieval_records(
        user_id=user_id,
        include_shared=include_shared,
        session_id=session_id,
        reasoning_layers=reasoning_layers,
        min_confidence=min_confidence,
        filters=filters,
    )

    category_hits = retrieve_category_hits(active_query, records, limit=max(3, min(6, limit)))
    selected_categories = [str(item.get("category", "")) for item in category_hits[:3] if str(item.get("category", ""))]
    category_sufficiency = evaluate_retrieval_sufficiency(
        active_query,
        [str(item.get("sample_text", "") or "") for item in category_hits if str(item.get("sample_text", "") or "")],
        stage="category",
    )

    candidate_records = filter_records_to_categories(records, selected_categories)
    if not candidate_records:
        candidate_records = list(records)
    item_records = rank_records(
        active_query,
        candidate_records,
        curated_importance=curated_importance,
        curated_mentions=curated_mentions,
        limit=limit,
        semantic_enabled=semantic_enabled,
        session_id=session_id,
    )
    item_hits = [serialize_hit(row) for row in item_records]
    item_sufficiency = evaluate_retrieval_sufficiency(
        active_query,
        [str(getattr(row, "text", "") or "") for row in item_records],
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
        resource_hits = retrieve_resource_hits(
            scopes=scopes,
            record_ids=[str(getattr(row, "id", "") or "") for row in item_records],
            limit=max(1, limit),
        )
        combined_texts = [str(getattr(row, "text", "") or "") for row in item_records] + [
            str(item.get("text", "") or "") for item in resource_hits
        ]
        resource_sufficiency = evaluate_retrieval_sufficiency(active_query, combined_texts, stage="resource")
    episodic_digest = synthesize_visible_episode_digest(
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


def refine_hits_with_llm(
    query: str,
    hits: list[dict[str, Any]],
    *,
    category_hits: list[dict[str, Any]] | None = None,
    resource_hits: list[dict[str, Any]] | None = None,
    run_completion: Callable[[str], Any],
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
        response = run_completion(prompt)
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


__all__ = [
    "build_progressive_retrieval_payload",
    "evaluate_retrieval_sufficiency",
    "filter_records_to_categories",
    "query_coverage",
    "refine_hits_with_llm",
    "retrieve_category_hits",
    "retrieve_resource_hits",
    "rewrite_retrieval_query",
]
