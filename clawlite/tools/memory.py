from __future__ import annotations

import json
import inspect
from typing import Any

from clawlite.core.memory import MemoryRecord, MemoryStore
from clawlite.tools.base import Tool, ToolContext


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _coerce_float(value: Any, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not parsed == parsed:
        return default
    if parsed in {float("inf"), float("-inf")}:
        return default
    return parsed


def _coerce_reasoning_layers(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    out: list[str] = []
    for item in value:
        text = str(item or "").strip().lower()
        if text:
            out.append(text)
    return out


def _memory_ref(memory_id: str) -> str:
    clean = str(memory_id or "").strip()
    short = clean[:8] if clean else "unknown"
    return f"mem:{short}"


def _normalize_ref_prefix(value: str) -> str:
    clean = str(value or "").strip().lower()
    if clean.startswith("mem:"):
        clean = clean[4:]
    return clean


def _truncate_text(value: str, *, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit]


def _dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _accepts_parameter(func: Any, parameter: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if parameter in signature.parameters:
        return True
    return any(item.kind == inspect.Parameter.VAR_KEYWORD for item in signature.parameters.values())


class MemoryRecallTool(Tool):
    name = "memory_recall"
    description = "Recall semantically related memory snippets with provenance refs."

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for memory retrieval."},
                "limit": {"type": "integer", "description": "Max results (clamped to 1..20)."},
                "include_metadata": {"type": "boolean", "description": "Include id/source/created_at fields."},
                "reasoning_layers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional reasoning-layer filters.",
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Optional minimum confidence filter.",
                },
            },
            "required": ["query"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")

        limit = _clamp_int(arguments.get("limit"), default=6, minimum=1, maximum=20)
        include_metadata = _coerce_bool(arguments.get("include_metadata"), default=True)
        reasoning_layers = _coerce_reasoning_layers(arguments.get("reasoning_layers"))
        min_confidence = _coerce_float(arguments.get("min_confidence"), default=None)
        rows: list[MemoryRecord] = []
        async_retrieved: list[dict[str, Any]] | None = None
        retrieve_fn = getattr(self.memory, "retrieve", None)
        if callable(retrieve_fn):
            try:
                retrieve_kwargs: dict[str, Any] = {"limit": limit, "method": "rag"}
                if _accepts_parameter(retrieve_fn, "user_id"):
                    retrieve_kwargs["user_id"] = ctx.user_id
                if _accepts_parameter(retrieve_fn, "include_shared"):
                    retrieve_kwargs["include_shared"] = True
                if reasoning_layers and _accepts_parameter(retrieve_fn, "reasoning_layers"):
                    retrieve_kwargs["reasoning_layers"] = reasoning_layers
                if min_confidence is not None and _accepts_parameter(retrieve_fn, "min_confidence"):
                    retrieve_kwargs["min_confidence"] = min_confidence
                try:
                    payload = await retrieve_fn(query, **retrieve_kwargs)
                except TypeError:
                    payload = await retrieve_fn(query, limit=limit, method="rag")
                if isinstance(payload, dict):
                    raw_hits = payload.get("hits", [])
                    if isinstance(raw_hits, list):
                        async_retrieved = [item for item in raw_hits if isinstance(item, dict)]
            except Exception:
                async_retrieved = None
        if async_retrieved is None:
            search_kwargs: dict[str, Any] = {"limit": limit}
            search_fn = getattr(self.memory, "search")
            if _accepts_parameter(search_fn, "user_id"):
                search_kwargs["user_id"] = ctx.user_id
            if _accepts_parameter(search_fn, "include_shared"):
                search_kwargs["include_shared"] = True
            if reasoning_layers and _accepts_parameter(search_fn, "reasoning_layers"):
                search_kwargs["reasoning_layers"] = reasoning_layers
            if min_confidence is not None and _accepts_parameter(search_fn, "min_confidence"):
                search_kwargs["min_confidence"] = min_confidence
            try:
                rows = search_fn(query, **search_kwargs)
            except TypeError:
                rows = search_fn(query, limit=limit)

        results: list[dict[str, Any]] = []
        if async_retrieved is not None:
            for row in async_retrieved:
                row_id = str(row.get("id", "") or "")
                item: dict[str, Any] = {
                    "ref": _memory_ref(row_id),
                    "text": str(row.get("text", "") or ""),
                }
                if include_metadata:
                    item["id"] = row_id
                    item["source"] = str(row.get("source", "") or "")
                    item["created_at"] = str(row.get("created_at", "") or "")
                    item["reasoning_layer"] = str(row.get("reasoning_layer", "") or "")
                    item["confidence"] = row.get("confidence")
                results.append(item)
        else:
            for row in rows:
                item = {
                    "ref": _memory_ref(row.id),
                    "text": str(row.text or ""),
                }
                if include_metadata:
                    item["id"] = str(row.id or "")
                    item["source"] = str(row.source or "")
                    item["created_at"] = str(row.created_at or "")
                    item["reasoning_layer"] = str(getattr(row, "reasoning_layer", "") or "")
                    item["confidence"] = getattr(row, "confidence", None)
                results.append(item)

        payload = {
            "status": "ok",
            "query": query,
            "count": len(results),
            "results": results,
        }
        return _dump_json(payload)


class MemoryLearnTool(Tool):
    name = "memory_learn"
    description = "Store a durable memory note with a source marker."

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Memory text to store."},
                "source": {"type": "string", "description": "Optional explicit source marker."},
                "reasoning_layer": {
                    "type": "string",
                    "description": "Optional reasoning layer (fact/hypothesis/decision/outcome).",
                },
                "confidence": {
                    "type": "number",
                    "description": "Optional confidence score for the stored memory.",
                },
            },
            "required": ["text"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        text = str(arguments.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")
        text = text[:4000]

        source = str(arguments.get("source", "")).strip() or f"memory_learn:{ctx.session_id}"
        reasoning_layer_raw = arguments.get("reasoning_layer")
        reasoning_layer = str(reasoning_layer_raw).strip().lower() if reasoning_layer_raw is not None else None
        if reasoning_layer == "":
            reasoning_layer = None
        confidence = _coerce_float(arguments.get("confidence"), default=None)
        row: MemoryRecord
        memorize_fn = getattr(self.memory, "memorize", None)
        if callable(memorize_fn):
            try:
                memorize_kwargs: dict[str, Any] = {"text": text, "source": source}
                if _accepts_parameter(memorize_fn, "user_id"):
                    memorize_kwargs["user_id"] = ctx.user_id
                if _accepts_parameter(memorize_fn, "shared"):
                    memorize_kwargs["shared"] = False
                if reasoning_layer is not None and _accepts_parameter(memorize_fn, "reasoning_layer"):
                    memorize_kwargs["reasoning_layer"] = reasoning_layer
                if confidence is not None and _accepts_parameter(memorize_fn, "confidence"):
                    memorize_kwargs["confidence"] = confidence
                try:
                    payload = await memorize_fn(**memorize_kwargs)
                except TypeError:
                    payload = await memorize_fn(text=text, source=source)
                record = payload.get("record") if isinstance(payload, dict) else None
                if isinstance(record, dict):
                    row = MemoryRecord(
                        id=str(record.get("id", "") or ""),
                        text=str(record.get("text", "") or text),
                        source=str(record.get("source", "") or source),
                        created_at=str(record.get("created_at", "") or ""),
                        category=str(record.get("category", "context") or "context"),
                        reasoning_layer=str(record.get("reasoning_layer", "") or "fact"),
                        confidence=float(record.get("confidence", 1.0) or 1.0),
                    )
                elif isinstance(payload, dict) and str(payload.get("status", "")).strip().lower() == "skipped":
                    return _dump_json(
                        {
                            "status": "skipped",
                            "ref": "",
                            "id": "",
                            "source": source,
                            "created_at": "",
                            "chars": len(text),
                            "reasoning_layer": reasoning_layer or "",
                            "confidence": confidence,
                        }
                    )
                else:
                    add_fn = getattr(self.memory, "add")
                    add_kwargs: dict[str, Any] = {"source": source}
                    if _accepts_parameter(add_fn, "user_id"):
                        add_kwargs["user_id"] = ctx.user_id
                    if _accepts_parameter(add_fn, "shared"):
                        add_kwargs["shared"] = False
                    if reasoning_layer is not None and _accepts_parameter(add_fn, "reasoning_layer"):
                        add_kwargs["reasoning_layer"] = reasoning_layer
                    if confidence is not None and _accepts_parameter(add_fn, "confidence"):
                        add_kwargs["confidence"] = confidence
                    try:
                        row = add_fn(text, **add_kwargs)
                    except TypeError:
                        row = add_fn(text, source=source)
            except Exception:
                add_fn = getattr(self.memory, "add")
                add_kwargs = {"source": source}
                if _accepts_parameter(add_fn, "user_id"):
                    add_kwargs["user_id"] = ctx.user_id
                if _accepts_parameter(add_fn, "shared"):
                    add_kwargs["shared"] = False
                if reasoning_layer is not None and _accepts_parameter(add_fn, "reasoning_layer"):
                    add_kwargs["reasoning_layer"] = reasoning_layer
                if confidence is not None and _accepts_parameter(add_fn, "confidence"):
                    add_kwargs["confidence"] = confidence
                try:
                    row = add_fn(text, **add_kwargs)
                except TypeError:
                    row = add_fn(text, source=source)
        else:
            add_fn = getattr(self.memory, "add")
            add_kwargs = {"source": source}
            if _accepts_parameter(add_fn, "user_id"):
                add_kwargs["user_id"] = ctx.user_id
            if _accepts_parameter(add_fn, "shared"):
                add_kwargs["shared"] = False
            if reasoning_layer is not None and _accepts_parameter(add_fn, "reasoning_layer"):
                add_kwargs["reasoning_layer"] = reasoning_layer
            if confidence is not None and _accepts_parameter(add_fn, "confidence"):
                add_kwargs["confidence"] = confidence
            try:
                row = add_fn(text, **add_kwargs)
            except TypeError:
                row = add_fn(text, source=source)

        payload = {
            "status": "ok",
            "ref": _memory_ref(row.id),
            "id": row.id,
            "source": row.source,
            "created_at": row.created_at,
            "chars": len(row.text),
            "reasoning_layer": str(getattr(row, "reasoning_layer", "") or ""),
            "confidence": getattr(row, "confidence", None),
        }
        return _dump_json(payload)


class MemoryForgetTool(Tool):
    name = "memory_forget"
    description = "Forget memory entries by ref/query/source with deterministic guardrails."

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Memory reference (mem:<id8>) or id prefix."},
                "query": {"type": "string", "description": "Search query used to select memory candidates."},
                "source": {"type": "string", "description": "Exact source filter."},
                "limit": {"type": "integer", "description": "Max deletions (clamped to 1..100)."},
                "dry_run": {"type": "boolean", "description": "Return planned deletions only."},
            },
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        ref = str(arguments.get("ref", "")).strip()
        query = str(arguments.get("query", "")).strip()
        source = str(arguments.get("source", "")).strip()
        if not ref and not query and not source:
            raise ValueError("selector is required")
        if query and len(query) < 3:
            raise ValueError("query must be at least 3 characters")

        limit = _clamp_int(arguments.get("limit"), default=10, minimum=1, maximum=100)
        dry_run = _coerce_bool(arguments.get("dry_run"), default=False)

        history_rows = self.memory.all()
        curated_rows = self.memory.curated()
        all_rows = history_rows + curated_rows

        query_ids: set[str] | None = None
        if query:
            query_matches = self.memory.search(query, limit=100)
            query_ids = {str(item.id or "").strip() for item in query_matches if str(item.id or "").strip()}

        ref_prefix = _normalize_ref_prefix(ref)
        candidates = []
        for row in all_rows:
            row_id = str(row.id or "").strip()
            if not row_id:
                continue
            if ref_prefix and not row_id.lower().startswith(ref_prefix):
                continue
            if source and str(row.source or "") != source:
                continue
            if query_ids is not None and row_id not in query_ids:
                continue
            candidates.append(row)

        candidates.sort(key=lambda row: (self.memory._parse_iso_timestamp(row.created_at), str(row.id or "")), reverse=True)

        selected_ids: list[str] = []
        seen: set[str] = set()
        for row in candidates:
            row_id = str(row.id or "").strip()
            if not row_id or row_id in seen:
                continue
            seen.add(row_id)
            selected_ids.append(row_id)
            if len(selected_ids) >= limit:
                break

        refs = [_memory_ref(row_id) for row_id in selected_ids]
        selectors = {
            "ref": ref,
            "query": query,
            "source": source,
            "dry_run": dry_run,
        }

        if not selected_ids:
            return _dump_json(
                {
                    "status": "not_found",
                    "deleted_count": 0,
                    "history_deleted": 0,
                    "curated_deleted": 0,
                    "limit": limit,
                    "selectors": selectors,
                    "refs": refs,
                }
            )

        if dry_run:
            return _dump_json(
                {
                    "status": "ok",
                    "deleted_count": 0,
                    "history_deleted": 0,
                    "curated_deleted": 0,
                    "limit": limit,
                    "selectors": selectors,
                    "refs": refs,
                }
            )

        deleted = self.memory.delete_by_prefixes(selected_ids, limit=limit)
        return _dump_json(
            {
                "status": "ok" if int(deleted.get("deleted_count", 0)) > 0 else "not_found",
                "deleted_count": int(deleted.get("deleted_count", 0)),
                "history_deleted": int(deleted.get("history_deleted", 0)),
                "curated_deleted": int(deleted.get("curated_deleted", 0)),
                "limit": limit,
                "selectors": selectors,
                "refs": refs,
            }
        )


class MemoryAnalyzeTool(Tool):
    name = "memory_analyze"
    description = "Analyze memory footprint and optional query matches."

    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional query for matching examples."},
                "limit": {"type": "integer", "description": "Max query matches (clamped to 1..20)."},
                "include_examples": {"type": "boolean", "description": "Include truncated text examples."},
            },
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        query = str(arguments.get("query", "")).strip()
        limit = _clamp_int(arguments.get("limit"), default=5, minimum=1, maximum=20)
        include_examples = _coerce_bool(arguments.get("include_examples"), default=True)

        stats = self.memory.analysis_stats()
        payload: dict[str, Any] = {
            "status": "ok",
            "counts": stats["counts"],
            "recent": stats["recent"],
            "temporal_marked_count": stats["temporal_marked_count"],
            "top_sources": stats["top_sources"],
        }
        if isinstance(stats.get("categories"), dict):
            payload["categories"] = stats["categories"]
        if isinstance(stats.get("reasoning_layers"), dict):
            payload["reasoning_layers"] = stats["reasoning_layers"]
        if isinstance(stats.get("confidence"), dict):
            payload["confidence"] = stats["confidence"]
        if isinstance(stats.get("semantic"), dict):
            payload["semantic"] = stats["semantic"]

        if query:
            payload["query"] = query
            matches = self.memory.search(query, limit=limit)
            out_matches: list[dict[str, Any]] = []
            for row in matches:
                item: dict[str, Any] = {
                    "ref": _memory_ref(row.id),
                    "source": str(row.source or ""),
                    "created_at": str(row.created_at or ""),
                }
                if include_examples:
                    item["text"] = _truncate_text(str(row.text or ""), limit=180)
                out_matches.append(item)
            payload["matches"] = out_matches

        return _dump_json(payload)
