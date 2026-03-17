from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable


def filter_records_to_categories(records: list[Any], categories: list[str]) -> list[Any]:
    allowed = {str(item or "").strip().lower() for item in categories if str(item or "").strip()}
    if not allowed:
        return list(records)
    return [row for row in records if str(getattr(row, "category", "context") or "context").strip().lower() in allowed]


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
    "filter_records_to_categories",
    "refine_hits_with_llm",
    "retrieve_resource_hits",
]
