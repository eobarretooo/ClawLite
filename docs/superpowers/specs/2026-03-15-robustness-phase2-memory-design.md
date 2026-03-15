# Robustness Phase 2 — memory (aligned with memU)

**Goal:** Elevate ClawLite memory from flat records to a structured, proactive, LLM-driven system aligned with memU's patterns.

**References:** `clawlite/core/memory.py`, `clawlite/core/memory_backend.py`, `/root/build/memU/`

---

## Architecture

### Current State

ClawLite memory: flat `MemoryRecord` objects with `layer` (history/curated), `category`, `reasoning_layer`, temporal decay, BM25 + vector search. Working memory promotion from session → episodic. Consolidation is deterministic (group by category, merge text).

memU pattern: hierarchical `Resource → Category → Item`. Resources are contexts (projects, people, conversations). Items belong to categories inside a resource. Proactive retrieval pre-loads context before turns. Consolidation uses LLM to produce natural-language summaries.

### Changes (additive, not breaking)

#### 2.1 ResourceContext — hierarchical grouping

New `ResourceContext` dataclass: `{id, name, kind: "project"|"person"|"conversation"|"document", description, tags, created_at, updated_at}`. Stored in a new `resources` table in the backend.

`MemoryRecord` gains an optional `resource_id: str` field. Existing records have `resource_id = None` (ungrouped). New records can be tagged with a resource at store time.

`MemoryStore.get_resource(resource_id)` → returns all records belonging to that resource, sorted by recency.

Use case: agent remembers "Project ClawLite" as a resource, and all related memories are grouped under it. Recall by resource gives coherent context blocks.

#### 2.2 Proactive Retrieval Pipeline

New `ProactiveContextLoader`: background task that runs before each turn (triggered by engine pre-turn hook). Algorithm:
1. Extract topics from incoming `user_text` (simple noun extraction, no LLM call)
2. Semantic search for each topic (limit 3 per topic)
3. Merge with recency-weighted results from `recent_context()`
4. Cache result in `_proactive_cache[session_id]` with 30s TTL

Engine reads from cache in `_plan_memory_snippets()` before falling back to on-demand recall. Net effect: memory is pre-warmed for common conversation patterns.

#### 2.3 LLM-driven Consolidation

Replace deterministic consolidation with `LLMConsolidator`:
- Groups N episodic records by category (existing logic)
- Calls LLM with: `"Summarize these N memories into 2-3 key facts: {records}"`
- Stores result as a curated knowledge record with `source="llm_consolidation"`, `confidence=0.85`
- Original episodic records marked `consolidated=True` (not deleted, just filtered from default recall)

Falls back to deterministic merge if LLM unavailable. LLM consolidation runs in `memory_monitor.py` consolidation loop (already async).

#### 2.4 Multi-modal Ingest

`MemoryStore.memorize()` already has `modality` and `file_path` fields. Add `ingest_file(path)` helper that:
- Detects MIME type
- For `.pdf`: uses `PdfReadTool` to extract text, then calls `memorize(text=extracted, modality="document")`
- For `.txt`/`.md`: direct ingest
- For audio: calls `TranscriptionProvider`, then `memorize(text=transcript, modality="audio")`

No schema changes — existing fields are sufficient.

#### 2.5 Field-level TTL (privacy layer)

New `MemoryTTLPolicy`: `{record_id, expires_at}` stored in a separate `memory_ttl` table. Background loop in `memory_monitor.py` purges expired records. Configurable per `source`:
- `source="session"` → default TTL 7 days (configurable)
- `source="user"` → no TTL (permanent)
- `source="llm_consolidation"` → no TTL

---

## Components

| File | Action |
|------|--------|
| `clawlite/core/memory_backend.py` | Modify — add `resources` table, `memory_ttl` table, CRUD methods |
| `clawlite/core/memory.py` | Modify — `ResourceContext`, `resource_id` on records, `get_resource()`, `ingest_file()`, TTL policy |
| `clawlite/core/memory_proactive.py` | New — `ProactiveContextLoader` |
| `clawlite/core/memory_consolidator.py` | New — `LLMConsolidator`, replaces inline consolidation logic |
| `clawlite/core/memory_monitor.py` | Modify — add TTL purge loop, call `LLMConsolidator` |
| `clawlite/core/engine.py` | Modify — pre-turn hook for `ProactiveContextLoader` |
| `tests/core/test_memory_resources.py` | New |
| `tests/core/test_memory_proactive.py` | New |
| `tests/core/test_memory_consolidator.py` | New |
| `tests/core/test_memory_ttl.py` | New |

---

## Error Handling

- LLM consolidation fails → fallback to deterministic merge, log warning
- Proactive loader timeout (>500ms) → skip cache, proceed with on-demand recall
- File ingest unsupported MIME → return `{"ok": false, "reason": "unsupported_modality"}`
- TTL purge error → log, skip record, continue loop

---

## Testing Strategy

- `test_memory_resources.py`: create resource, tag records, `get_resource()` returns correct records; ungrouped records unaffected
- `test_memory_proactive.py`: mock search, assert cache populated, assert cache TTL expiry, assert engine uses cache
- `test_memory_consolidator.py`: mock LLM call, assert curated record created with correct text; assert fallback on LLM error
- `test_memory_ttl.py`: insert record with short TTL, advance clock, run purge loop, assert deleted

---

## Success Criteria

- [ ] `ResourceContext` creates, reads, deletes without breaking existing flat records
- [ ] Proactive loader pre-warms cache and engine uses it in `_plan_memory_snippets`
- [ ] LLM consolidation produces curated records; falls back cleanly
- [ ] `ingest_file()` works for PDF, TXT, MD
- [ ] TTL purge removes expired records in monitor loop
- [ ] All new tests pass, 0 regressions
