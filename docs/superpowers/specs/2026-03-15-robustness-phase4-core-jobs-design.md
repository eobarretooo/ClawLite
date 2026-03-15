# Robustness Phase 4 — core + jobs

**Goal:** Context window budget management in engine, `jobs/` module for one-off async tasks, improved loop detection telemetry, and subagent parent/child context propagation.

**References:** `clawlite/core/engine.py`, `clawlite/core/subagent.py`, `clawlite/runtime/autonomy.py`

---

## Architecture

### core / engine

#### 4.1 Context Window Budget

Current: history is read with `limit=self.memory_window` (fixed count). No awareness of token count vs model context limit.

Change: `ContextWindowManager` — given a list of messages and a `max_tokens` budget (read from provider's model catalog), trims oldest history messages until estimated token count fits. Estimation: `len(text) // 4` (conservative char-to-token ratio).

`Engine.run()` calls `ContextWindowManager.trim(messages, budget=model_context_tokens * 0.85)` before provider call. The 0.85 factor reserves 15% for the response.

Config: `agents.defaults.context_budget_ratio: float = 0.85`. Per-agent override via `agents.by_name.<name>.context_budget_ratio`.

#### 4.2 Loop Detection Telemetry → Bus

Current: loop detection logs and breaks. Loop events are invisible to external observers.

Change: when loop detected, emit `InboundEvent(channel="_system", text="loop_detected", metadata={...})` on the bus. `RuntimeSupervisor` subscribes to `_system` channel and can trigger recovery actions. No behavior change — just adds observability.

#### 4.3 Turn Budget as Resource

`TurnBudget` already exists as a dataclass. Harden:
- `soft_limit_iterations` → emit `progress(stage="budget_warning")` when reached
- `hard_limit_iterations` → stop loop, emit `progress(stage="budget_exceeded")`, return partial result
- `max_tool_calls` (new) → per-turn tool call cap. Prevents tool storms.
- `token_budget` (new) → abort if accumulated response tokens exceed limit

---

### jobs (new module)

#### 4.4 `clawlite/jobs/` — One-Off Async Job Queue

**Problem:** `cron` handles recurring jobs. `autonomy` handles wake events. There's no clean way to submit a one-off background task (e.g., "summarize this document", "run a research query") that:
- Has a unique ID
- Can be status-checked
- Can be cancelled
- Has priority
- Persists across restarts (optional)

**Design:** `JobQueue` — thin async worker pool built on top of existing `AutonomyWakeCoordinator` patterns.

```python
@dataclass
class Job:
    id: str           # uuid hex
    kind: str         # "agent_run" | "skill_exec" | "custom"
    payload: dict     # arbitrary task data
    priority: int     # 0=low, 5=normal, 10=high
    session_id: str
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    result: str
    error: str
    created_at: str
    started_at: str
    finished_at: str
    max_retries: int  # default 0 (no retry)
    retry_count: int
```

`JobQueue` dispatches by `kind` via a registered worker function:
- `"agent_run"` → calls `engine.run(session_id=job.session_id, user_text=job.payload["prompt"])` — runs a full agent turn and returns the text response
- `"skill_exec"` → calls `tool_registry.execute("run_skill", {"name": job.payload["skill"], **job.payload.get("args", {})}, session_id=job.session_id)` — runs a skill directly
- `"custom"` → calls `JobQueue._custom_dispatch[job.payload["handler"]](job)` — extensible hook for non-standard job types; handlers registered at startup via `queue.register_custom(handler_name, fn)`

`JobQueue`:
- `submit(kind, payload, *, priority=5, session_id, max_retries=0) -> Job`
- `status(job_id) -> Job | None`
- `cancel(job_id) -> bool`
- `list_jobs(session_id=None, status=None) -> list[Job]`
- `start(worker_fn, *, concurrency=2)` — starts N worker coroutines
- `stop()` — drains queue, cancels in-flight

Worker dispatch: `worker_fn(job: Job) -> str` — returns result string.

Persistence: optional SQLite journal (same pattern as `BusJournal`). Enabled via `config.jobs.persist_enabled`.

Tool integration: new `JobsTool` (name: `"jobs"`) — agent can submit, check, and list jobs. Registered alongside other tools.

CLI: `clawlite jobs list`, `clawlite jobs status <id>`, `clawlite jobs cancel <id>`.

---

### subagent improvements

#### 4.5 Parent/Child Context Propagation

Current: `SubagentManager.spawn()` takes `session_id` and `task` — child agent starts with empty context.

Change: `spawn()` gains `parent_session_id: str` optional param. When set:
- Child `session_id` is prefixed `"{parent_session_id}:sub:{run_id[:8]}"`
- Child inherits last N messages from parent session as initial context (read-only snapshot, not live)
- Child's result is posted back to parent session as a tool result message

This makes subagent work visible in parent conversation history.

---

## Components

| File | Action |
|------|--------|
| `clawlite/core/context_window.py` | New — `ContextWindowManager` |
| `clawlite/core/engine.py` | Modify — use `ContextWindowManager`, bus loop events, hardened `TurnBudget` |
| `clawlite/core/subagent.py` | Modify — `parent_session_id`, context inheritance |
| `clawlite/jobs/__init__.py` | New |
| `clawlite/jobs/queue.py` | New — `Job`, `JobQueue` |
| `clawlite/jobs/journal.py` | New — SQLite persistence (mirrors `BusJournal` pattern) |
| `clawlite/tools/jobs.py` | New — `JobsTool` |
| `clawlite/config/schema.py` | Modify — add `JobsConfig` sub-schema |
| `gateway/server.py` | Modify — register `JobsTool`, jobs API endpoints |
| `clawlite/cli/commands.py` | Modify — add `jobs` command group |
| `tests/core/test_context_window.py` | New |
| `tests/jobs/test_queue.py` | New |
| `tests/jobs/test_journal.py` | New |
| `tests/tools/test_jobs_tool.py` | New |

---

## Error Handling

- `ContextWindowManager` trim error → log warning, use untrimmed messages (safe degradation)
- Job worker exception → job status `"failed"`, error saved, retry if `max_retries > retry_count`
- Job cancel while running → set `cancellation_requested` flag, worker checks between tool calls
- Subagent context inheritance error → spawn with empty context (existing behavior), log warning

---

## Testing Strategy

- `test_context_window.py`: messages exceeding budget → trimmed to fit; messages within budget → untouched; trim preserves system message
- `test_queue.py`: submit/status/cancel lifecycle; priority ordering (high before low); concurrency (2 workers, 4 jobs → runs 2 at a time)
- `test_journal.py`: submit job, simulate restart, assert job restored in `queued` state
- `test_jobs_tool.py`: agent submits job via tool call, checks status, receives result

---

## Success Criteria

- [ ] `ContextWindowManager` trims messages when over budget, preserving system message
- [ ] Loop detection emits bus event (subscribable by supervisor)
- [ ] `TurnBudget.max_tool_calls` enforced in engine loop
- [ ] `JobQueue.submit()` → `status()` → `done` lifecycle works
- [ ] Jobs persist across restart when `persist_enabled=true`
- [ ] `clawlite jobs list` shows job statuses
- [ ] Subagent inherits parent context when `parent_session_id` set
- [ ] 0 regressions on existing engine tests
