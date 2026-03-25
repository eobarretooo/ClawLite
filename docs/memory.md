# Memory

ClawLite's memory layer is no longer just a flat JSONL log. The runtime still keeps a history file, but it now also maintains a structured memory home with indexes, privacy state, quality metrics, working memory, versions, and shared-memory metadata.

## Default Paths

When you use the default config paths, ClawLite stores memory in two places:

- history file: `~/.clawlite/state/memory.jsonl`
- structured memory home: `~/.clawlite/memory/`

This split is normal. The JSONL history remains the backward-compatible source log, while the structured memory home stores indexes and sidecar state.

## Config

Memory config lives under `agents.defaults.memory`:

```json
{
  "agents": {
    "defaults": {
      "memory": {
        "semantic_search": true,
        "auto_categorize": true,
        "proactive": true,
        "proactive_retry_backoff_s": 300.0,
        "proactive_max_retry_attempts": 3,
        "emotional_tracking": true,
        "backend": "sqlite",
        "pgvector_url": ""
      }
    }
  }
}
```

Current keys:

- `semantic_search`
- `auto_categorize`
- `proactive`
- `proactive_retry_backoff_s`
- `proactive_max_retry_attempts`
- `emotional_tracking`
- `backend`
- `pgvector_url`

Notes:

- `backend` accepts `sqlite` and `pgvector`.
- legacy `jsonl` is normalized to `sqlite`.
- legacy `semantic_memory` and `memory_auto_categorize` still map into the nested memory config.

## Backends

### `sqlite` (default)

- Always available.
- Persists local memory indexes in `~/.clawlite/memory/memory-index.sqlite3`.
- Keeps the JSONL history file for compatibility.

### `pgvector`

- Optional.
- Requires a valid PostgreSQL DSN in `agents.defaults.memory.pgvector_url`.
- Startup fails fast if the driver, DSN, or `pgvector` extension support is missing.

The gateway explicitly validates `pgvector` at runtime. If support is missing, it tells you to either configure `pgvector_url` correctly or switch back to `sqlite`.

## Memory Home Layout

The structured memory home can contain these paths:

```text
~/.clawlite/memory/
|- resources/
|- items/
|- categories/
|- embeddings/
|  `- embeddings.jsonl
|- emotional/
|  `- profile.json
|- users/
|- shared/
|  `- optin.json
|- versions/
|  |- HEAD
|  `- branches.json
|- privacy.json
|- privacy.key
|- privacy-audit.jsonl
|- quality-state.json
|- working-memory.json
`- memory-index.sqlite3
```

Other compatibility files can still exist next to the history log, such as:

- `memory_curated.json`
- `memory_checkpoints.json`

## What the Runtime Tracks

### Durable memory

Durable memory is stored through the history log and structured items/categories/resources.

This powers:

- normal search and retrieval
- provenance-aware memory results
- category and reasoning-layer analysis
- branch, snapshot, export, and merge flows

### Working memory

`working-memory.json` stores short-lived per-session state such as:

- recent message buffers
- share scopes such as `private`, `parent`, and `family`
- promotion state before content is committed into durable memory

### Quality state

`quality-state.json` tracks memory quality over time. The runtime uses it to decide whether memory writes, skill execution, and subagent spawning should stay fully enabled, become restricted, or be blocked.
The snapshot now also includes a compact `trend` summary derived from the bounded history window, so dashboard, diagnostics, and CLI flows can show whether quality is improving, stable, or degrading without recomputing the full history client-side.

### Emotional/profile state

`emotional/profile.json` stores the user profile used by memory-aware prompting, including language, timezone, response length preference, recurring interests, and upcoming events.

## Privacy Model

Privacy rules live in `privacy.json`.

Default behavior includes:

- `never_memorize_patterns`: blocks obvious secret-like content such as `senha`, `cpf`, `cartao`, `token`, and `api_key`
- `ephemeral_categories`: categories that should expire automatically
- `ephemeral_ttl_days`: default TTL for ephemeral categories
- `encrypted_categories`: categories that should be encrypted at rest
- `audit_log`: writes privacy audit records to `privacy-audit.jsonl`

If encrypted categories are configured, ClawLite manages the local key in `privacy.key`.

## Retrieval Behavior

`memory_search` and normal agent retrieval prefer the async retrieval path when available:

- method: `rag`
- optional filters: reasoning layers and minimum confidence
- optional inclusion of shared memory

When semantic retrieval is unavailable, ClawLite falls back to the local search path.

## Snapshots, Branches, and Sharing

The CLI exposes first-class versioning operations:

```bash
clawlite memory snapshot --tag before-upgrade
clawlite memory version
clawlite memory rollback <id>
clawlite memory branches
clawlite memory branch experiment --checkout
clawlite memory checkout main
clawlite memory merge --source experiment --target main --tag merge
clawlite memory share-optin --user alice --enabled true
```

Key files behind those commands:

- `versions/HEAD`
- `versions/branches.json`
- `shared/optin.json`

## Proactive Memory Monitor

When `agents.defaults.memory.proactive=true`, the gateway creates a `MemoryMonitor`.

That enables:

- proactive suggestion scans
- retry/backoff handling for proactive delivery
- telemetry in diagnostics under `memory_monitor`

The retry knobs are:

- `proactive_retry_backoff_s`
- `proactive_max_retry_attempts`

## Quality-Based Integration Policy

Memory quality influences runtime policy for four actor classes:

- `system`
- `agent`
- `subagent`
- `tool`

Depending on the current quality score and drift state, ClawLite can:

- keep everything normal
- reduce search limits
- block skill execution for delegated actors
- block subagent spawning
- block memory writes in severe mode

This policy is why some memory-using tools can become more conservative during degraded runs.

## Useful Commands

```bash
clawlite memory
clawlite memory doctor
clawlite memory doctor --repair
clawlite memory eval --limit 5
clawlite memory quality --gateway-url http://127.0.0.1:8787
clawlite memory profile
clawlite memory privacy
clawlite memory suggest
clawlite memory export --out ./memory-export.json
clawlite memory import ./memory-export.json
```

The packaged dashboard now also exposes two first-class memory control-plane actions:

- `Run memory doctor`, backed by `POST /v1/control/memory/doctor` and `POST /api/memory/doctor`, which keeps the existing read-only file-integrity snapshot available on demand
- `Run memory overview`, backed by `POST /v1/control/memory/overview` and `POST /api/memory/overview`, which returns a lightweight live snapshot of counts, semantic coverage, proactive-memory posture, and memory file locations
- `Run memory quality`, backed by `POST /v1/control/memory/quality` and `POST /api/memory/quality`, which computes and persists a fresh quality-state report from the running runtime

Those live snapshots stay separate from the normal dashboard-state payload on purpose, so operators can inspect integrity, overview, and quality signals on demand without turning every generic dashboard refresh into a heavier memory maintenance cycle.

The same Memory card now also turns those read-only signals into a more guided triage surface: it highlights the top live quality recommendation and the highest-priority pending proactive-memory suggestion directly in the dashboard instead of leaving that interpretation entirely to raw JSON or the CLI.

## Session Logs vs Memory

Session logs are not the same as memory.

- Session logs live under `~/.clawlite/state/sessions/*.jsonl`.
- Memory lives in `~/.clawlite/state/memory.jsonl` plus `~/.clawlite/memory/`.

The sessions tools operate on session logs; the memory tools operate on structured memory and durable recall.
