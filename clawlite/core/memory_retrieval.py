from __future__ import annotations

from collections import deque
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


def curated_records(
    rows: list[dict[str, Any]],
    *,
    record_cls: type,
    user_id: str,
    normalize_layer: Callable[[Any], str],
    normalize_reasoning_layer: Callable[[Any], str],
    normalize_confidence: Callable[..., float],
    normalize_decay_rate: Callable[..., float],
    default_decay_rate: Callable[..., float],
    normalize_memory_type: Callable[[Any], str],
    normalize_memory_metadata: Callable[[Any], dict[str, Any]],
) -> list[Any]:
    out: list[Any] = []
    for item in rows:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        memory_type = normalize_memory_type(item.get("memory_type", item.get("memoryType", "knowledge")))
        out.append(
            record_cls(
                id=str(item.get("id", "")),
                text=text,
                source=str(item.get("source", "curated")),
                created_at=str(item.get("created_at", "")),
                category=str(item.get("category", "context") or "context"),
                user_id=str(user_id or "default"),
                layer=normalize_layer(item.get("layer", "item")),
                reasoning_layer=normalize_reasoning_layer(item.get("reasoning_layer", item.get("reasoningLayer", "fact"))),
                modality=str(item.get("modality", "text") or "text"),
                confidence=normalize_confidence(item.get("confidence", 1.0), default=1.0),
                decay_rate=normalize_decay_rate(
                    item.get(
                        "decay_rate",
                        item.get("decayRate", default_decay_rate(memory_type=memory_type)),
                    ),
                    default=0.0,
                ),
                memory_type=memory_type,
                happened_at=str(item.get("happened_at", item.get("happenedAt", "")) or ""),
                metadata=normalize_memory_metadata(item.get("metadata", {})),
            )
        )
    return out


def list_recent_candidates(
    *,
    source: str,
    ref_prefix: str,
    limit: int,
    max_scan: int,
    fetch_layer_records: Callable[..., list[Any]],
    record_from_payload: Callable[[dict[str, Any]], Any | None],
    decrypt_text_for_category: Callable[[str, str], str],
    normalize_prefix: Callable[[str], str],
    record_sort_key: Callable[[Any], Any],
    history_path: Path,
    locked_file: Callable[..., Any],
    read_curated_facts: Callable[[], list[dict[str, Any]]],
    item_layer_value: str,
) -> list[Any]:
    bounded_limit = max(1, int(limit or 1))
    bounded_scan = max(bounded_limit, min(max(1, int(max_scan or bounded_limit)), 5000))
    clean_source = str(source or "").strip()
    clean_prefix = normalize_prefix(ref_prefix)

    out: list[Any] = []
    seen_ids: set[str] = set()

    def _accept(row: Any | None) -> bool:
        if row is None:
            return False
        row_id = str(getattr(row, "id", "") or "").strip()
        if not row_id or row_id in seen_ids:
            return False
        if clean_prefix and not normalize_prefix(row_id).startswith(clean_prefix):
            return False
        if clean_source and str(getattr(row, "source", "") or "") != clean_source:
            return False
        seen_ids.add(row_id)
        out.append(row)
        return len(out) >= bounded_limit

    try:
        backend_rows = fetch_layer_records(layer=item_layer_value, limit=bounded_scan)
    except Exception:
        backend_rows = []
    for row in backend_rows:
        if not isinstance(row, dict):
            continue
        payload = row.get("payload", {})
        if not isinstance(payload, dict):
            continue
        candidate = record_from_payload(payload)
        if candidate is None:
            continue
        candidate.text = decrypt_text_for_category(str(getattr(candidate, "text", "") or ""), getattr(candidate, "category", "context"))
        if _accept(candidate):
            return out

    with locked_file(history_path, "r", exclusive=False) as fh:
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
        candidate = record_from_payload(payload)
        if candidate is None:
            continue
        candidate.text = decrypt_text_for_category(str(getattr(candidate, "text", "") or ""), getattr(candidate, "category", "context"))
        if _accept(candidate):
            return out

    for item in read_curated_facts():
        candidate = record_from_payload(item)
        if candidate is None:
            continue
        if _accept(candidate):
            return out

    out.sort(key=record_sort_key, reverse=True)
    return out[:bounded_limit]


def resolve_retrieval_scopes(
    *,
    user_id: str,
    include_shared: bool,
    normalize_user_id: Callable[[str], str],
    shared_opt_in: Callable[[str], bool],
    scope_paths: Callable[..., dict[str, Path]],
    ensure_scope_paths: Callable[[dict[str, Path]], None],
) -> list[dict[str, Path]]:
    clean_user = normalize_user_id(user_id or "default")
    scopes: list[dict[str, Path]] = [scope_paths(user_id=clean_user, shared=False)]
    if clean_user != "default" and include_shared and shared_opt_in(clean_user):
        scopes.append(scope_paths(shared=True))
    for scope in scopes:
        ensure_scope_paths(scope)
    return scopes


def collect_retrieval_records(
    *,
    user_id: str,
    include_shared: bool,
    session_id: str,
    reasoning_layers: Iterable[str] | None,
    min_confidence: float | None,
    filters: dict[str, Any] | None,
    normalize_user_id: Callable[[str], str],
    normalize_reasoning_layers_filter: Callable[[Iterable[str] | None], set[str]],
    normalize_confidence: Callable[..., float],
    normalize_retrieval_filters: Callable[[dict[str, Any] | None], dict[str, Any]],
    resolve_retrieval_scopes_fn: Callable[..., list[dict[str, Path]]],
    shared_root: Path,
    read_curated_facts_from: Callable[[Path], list[dict[str, Any]]],
    read_history_records_from: Callable[[Path], list[Any]],
    curated_records_fn: Callable[..., list[Any]],
    apply_retrieval_filters: Callable[[list[Any], dict[str, Any]], list[Any]],
    working_episode_visible_in_session: Callable[[Any, str], bool],
    semantic_enabled: bool,
) -> tuple[list[Any], dict[str, float], dict[str, int], list[dict[str, Path]], bool]:
    clean_user = normalize_user_id(user_id or "default")
    reasoning_filter = normalize_reasoning_layers_filter(reasoning_layers)
    min_conf_filter = normalize_confidence(min_confidence, default=0.0) if min_confidence is not None else None
    normalized_filters = normalize_retrieval_filters(filters)
    scopes = resolve_retrieval_scopes_fn(user_id=clean_user, include_shared=include_shared)

    records: list[Any] = []
    curated_importance: dict[str, float] = {}
    curated_mentions: dict[str, int] = {}

    for scope in scopes:
        scope_user_id = "shared" if Path(scope["root"]) == shared_root else clean_user
        curated_rows = read_curated_facts_from(scope["curated"])
        curated_records = curated_records_fn(curated_rows, user_id=scope_user_id)
        records.extend(curated_records)
        for item, row in zip(curated_rows, curated_records, strict=False):
            row_id = str(getattr(row, "id", "") or "")
            if not row_id:
                continue
            try:
                curated_importance[row_id] = float(item.get("importance", 1.0) or 1.0)
            except Exception:
                curated_importance[row_id] = 1.0
            try:
                curated_mentions[row_id] = int(item.get("mentions", 1) or 1)
            except Exception:
                curated_mentions[row_id] = 1

        records.extend(read_history_records_from(scope["history"]))

    records = apply_retrieval_filters(records, normalized_filters)
    if reasoning_filter:
        records = [row for row in records if str(getattr(row, "reasoning_layer", "") or "").strip().lower() in reasoning_filter]
    if min_conf_filter is not None:
        records = [
            row
            for row in records
            if normalize_confidence(getattr(row, "confidence", 1.0), default=1.0) >= min_conf_filter
        ]
    if session_id:
        records = [row for row in records if working_episode_visible_in_session(row, session_id=session_id)]

    return records, curated_importance, curated_mentions, scopes, bool(semantic_enabled and records)


def recover_session_context(
    session_id: str,
    *,
    limit: int,
    diagnostics: dict[str, Any],
    source_session_key: Callable[[str], str],
    get_working_set: Callable[..., list[dict[str, Any]]],
    read_history_records: Callable[[], list[Any]],
    read_curated_facts: Callable[[], list[dict[str, Any]]],
) -> list[str]:
    diagnostics["session_recovery_attempts"] = int(diagnostics.get("session_recovery_attempts", 0) or 0) + 1
    bounded_limit = max(1, int(limit or 1))
    clean_session_id = str(session_id or "").strip()
    normalized_targets = {
        clean_session_id,
        f"session:{clean_session_id}" if clean_session_id else "",
    }
    normalized_targets.discard("")
    normalized_session_targets = {
        source_session_key(clean_session_id),
        source_session_key(f"session:{clean_session_id}"),
    }

    picked: list[str] = []
    seen: set[str] = set()

    working_rows = get_working_set(clean_session_id, limit=bounded_limit, include_shared_subagents=True)
    for entry in working_rows:
        snippet = str(entry.get("content", "") or "").strip()
        if not snippet or snippet in seen:
            continue
        seen.add(snippet)
        picked.append(snippet)
        if len(picked) >= bounded_limit:
            break

    history_rows = read_history_records()
    for row in reversed(history_rows):
        if str(getattr(row, "source", "") or "") not in normalized_targets:
            continue
        snippet = str(getattr(row, "text", "") or "").strip()
        if not snippet or snippet in seen:
            continue
        seen.add(snippet)
        picked.append(snippet)
        if len(picked) >= bounded_limit:
            break

    if len(picked) < bounded_limit:
        for fact in read_curated_facts():
            sessions = fact.get("sessions", [])
            if not isinstance(sessions, list):
                continue
            normalized_sessions = {source_session_key(str(item or "")) for item in sessions}
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
        diagnostics["session_recovery_hits"] = int(diagnostics.get("session_recovery_hits", 0) or 0) + 1

    return picked


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
    "collect_retrieval_records",
    "curated_records",
    "evaluate_retrieval_sufficiency",
    "filter_records_to_categories",
    "list_recent_candidates",
    "query_coverage",
    "refine_hits_with_llm",
    "recover_session_context",
    "resolve_retrieval_scopes",
    "retrieve_category_hits",
    "retrieve_resource_hits",
    "rewrite_retrieval_query",
]
