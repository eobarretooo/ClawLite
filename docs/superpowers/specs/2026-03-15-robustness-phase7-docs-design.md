# Robustness Phase 7 — docs + README

**Goal:** Full documentation refresh reflecting all phases of this milestone. Every doc accurate to the final implemented state.

**References:** All docs in `docs/`, `README.md`, `ref/` projects for comparison context.

---

## Architecture

This phase is purely documentation. No code changes. All updates are based on the implemented state after phases 1–6.

---

## Documents to Update

### README.md

**Current:** 430 lines. Has architecture overview, comparison table (openclaw/nanobot), demo GIF, quickstart.

**Changes:**
- Update architecture diagram (text-based) to include `jobs/` module
- Add `bus journal`, `config hot-reload`, `context window budget` to feature list
- Update capability table: add memory proactive retrieval, structured identity, job queue
- Update comparison table: reflect new robustness features vs ref projects
- Keep demo GIF (unchanged)
- Add "What's New" section pointing to CHANGELOG

### STATUS.md

**Current:** Engineering snapshot as of 2026-03-15 (pre-robustness milestone).

**Changes:** Full rewrite to reflect post-milestone state:
- Test suite count (updated from 1186)
- All modules status: green
- New modules added: `jobs/`, `config/watcher.py`, `config/health.py`, `bus/journal.py`, `core/context_window.py`, `workspace/soul_parser.py`, etc.
- Known limitations section: what's intentionally out of scope (advanced channels, skill marketplace)

### CHANGELOG.md

**Changes:** Add `v1.0.0` section with all 7 phases listed:
- Phase 1: config hot-reload, bus journal, typed envelopes
- Phase 2: memory hierarchy, proactive retrieval, LLM consolidation, multi-modal ingest, TTL
- Phase 3: provider telemetry, streaming recovery, centralized tool timeout, result cache, health checks
- Phase 4: context window budget, job queue, subagent context propagation
- Phase 5: skills validation, dependency graph, cron categories, missed-job policy, chaining, export/import
- Phase 6: bootstrap flow, identity write-back, SOUL parser, drift detection

### API.md

**Changes:** Add new endpoints:
- `GET /health/config` — config health
- `GET /health/tools` — tool health checks
- `GET /health/providers` — provider warmup status
- `GET /health/identity` — workspace/identity health
- `GET /metrics/providers` — per-model telemetry
- Jobs API: `POST /jobs`, `GET /jobs/{id}`, `DELETE /jobs/{id}`, `GET /jobs`

### CONFIGURATION.md

**Changes:** Add new config sections:
- `bus.journal_enabled`, `bus.journal_path`
- `jobs.persist_enabled`, `jobs.persist_path`, `jobs.worker_concurrency`
- `agents.defaults.context_budget_ratio`
- `agents.defaults.max_tool_calls_per_turn`

### tools.md

**Changes:**
- Add `jobs` tool documentation
- Add `identity` tool documentation
- Update all tools to note centralized timeout (no per-tool config needed)
- Add `health_check` status column to tool table

### memory.md

**Changes:** Document new features:
- `ResourceContext` — hierarchical grouping
- Proactive retrieval — how/when it triggers
- LLM-driven consolidation — what it produces, fallback behavior
- `ingest_file()` — supported formats
- TTL policies — per-source defaults

### providers.md

**Changes:**
- Add telemetry section (`GET /metrics/providers`)
- Document `degraded=True` streaming behavior
- Add warmup probe section

### SKILLS.md

**Changes:**
- Add `requires` field documentation
- Add `version` field documentation
- Mark all 25 skills with their version (default `"1.0.0"`)

### ARCHITECTURE.md

**Changes:** Update diagram to include:
- `jobs/` module between `core/` and `scheduler/`
- `bus/journal.py` persistence layer
- `config/watcher.py` hot-reload path
- `workspace/soul_parser.py` in identity stack

---

## Components

| File | Action |
|------|--------|
| `README.md` | Update |
| `docs/STATUS.md` | Full rewrite |
| `docs/CHANGELOG.md` | Add v1.0.0 section |
| `docs/API.md` | Add new endpoints |
| `docs/CONFIGURATION.md` | Add new config fields |
| `docs/tools.md` | Add jobs+identity tools, timeout note |
| `docs/memory.md` | Add new memory features |
| `docs/providers.md` | Add telemetry + degraded stream |
| `docs/SKILLS.md` | Add requires/version fields |
| `docs/ARCHITECTURE.md` | Update diagram |

---

## Success Criteria

- [ ] README accurately reflects post-milestone architecture
- [ ] STATUS.md has current test count and module status
- [ ] CHANGELOG.md has complete v1.0.0 entry
- [ ] API.md documents all new endpoints from phases 1–6
- [ ] CONFIGURATION.md documents all new config fields
- [ ] All doc cross-references (links between docs) are valid
- [ ] No "TODO" or placeholder text remaining in updated docs
- [ ] Docs reviewed against actual implemented code (no doc/code drift)
