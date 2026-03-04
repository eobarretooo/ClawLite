from __future__ import annotations

import json
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
            },
            "required": ["query"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")

        limit = _clamp_int(arguments.get("limit"), default=6, minimum=1, maximum=20)
        include_metadata = _coerce_bool(arguments.get("include_metadata"), default=True)
        rows = self.memory.search(query, limit=limit)

        results: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {
                "ref": _memory_ref(row.id),
                "text": str(row.text or ""),
            }
            if include_metadata:
                item["id"] = str(row.id or "")
                item["source"] = str(row.source or "")
                item["created_at"] = str(row.created_at or "")
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
            },
            "required": ["text"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        text = str(arguments.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")
        text = text[:4000]

        source = str(arguments.get("source", "")).strip() or f"memory_learn:{ctx.session_id}"
        row: MemoryRecord = self.memory.add(text, source=source)

        payload = {
            "status": "ok",
            "ref": _memory_ref(row.id),
            "id": row.id,
            "source": row.source,
            "created_at": row.created_at,
            "chars": len(row.text),
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
