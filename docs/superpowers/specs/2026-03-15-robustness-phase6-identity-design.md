# Robustness Phase 6 — identity (workspace)

**Goal:** Automatic BOOTSTRAP completion, identity write-back, semantic drift detection, and structured SOUL.md engine.

**References:** `clawlite/workspace/`, `clawlite/workspace/identity_enforcer.py`, `clawlite/workspace/loader.py`

---

## Architecture

### 6.1 BOOTSTRAP Flow Completion

Current: `BOOTSTRAP.md` is loaded by `WorkspaceLoader.system_context()` on every turn if the file exists. The agent is supposed to delete it after first run, but this relies entirely on agent judgment.

Change: `WorkspaceLoader` tracks bootstrap completion in a `workspace_state.json` file alongside workspace files:
```json
{"bootstrap_complete": false, "bootstrap_completed_at": ""}
```

`WorkspaceLoader.mark_bootstrap_complete()` — sets flag and renames `BOOTSTRAP.md` → `BOOTSTRAP.md.done` (not deleted, auditable).

Engine integration: after each turn where `BOOTSTRAP.md` was included in context, check if agent response contains bootstrap completion signals (heuristic: response length > 100 chars and no tool errors). If yes, auto-call `mark_bootstrap_complete()`.

This ensures bootstrap doesn't persist forever if the agent never explicitly deletes the file.

### 6.2 Identity Write-Back

Current: agent can call `write_file` to update `IDENTITY.md`, but there's no structured API. The identity enforcer reads from the file but doesn't write to it.

Change: `IdentityEnforcer.update_identity(field, value)` — structured write-back:
- `field`: one of `"name"`, `"vibe"`, `"emoji"`, `"purpose"`, `"communication_style"`
- Reads current `IDENTITY.md`, finds the relevant section by heading, replaces placeholder or existing value
- Writes back atomically (write to `.tmp`, rename)
- Logs `identity.updated field={field}`

New tool: `identity_update` (name: `"identity"`) — agent calls `{"action": "update", "field": "name", "value": "Aria"}`. Returns `"identity_updated:name:Aria"`.

`WorkspaceLoader` exposes `load_identity_fields() -> dict[str, str]` — parses structured fields from `IDENTITY.md` for use in prompt variables.

### 6.3 Semantic Drift Detection

Current: `IdentityEnforcer` uses regex patterns to detect provider brand names and language model disclaimers. This misses paraphrased drift (e.g., "I was created by a team of researchers").

Change: `IdentityEnforcer.check_drift(text, identity_name)` gains a semantic layer:
- First pass: existing regex (fast, no LLM)
- Second pass (if first pass clean): simple string distance check — if response never mentions `identity_name` in a 200+ char response about the agent's identity, flag as potential drift
- Adds `drift_score: float` (0.0–1.0) to `EnforcementResult`. Score > 0.7 → violation; 0.4–0.7 → warning.

No LLM call in the enforcer (keeps it fast). The semantic layer is purely heuristic (name presence, prohibited phrases list from AGENTS.md).

### 6.4 SOUL.md Structured Engine

Current: `SOUL.md` is loaded as raw text and injected verbatim into the system prompt. No structure.

Change: `SoulParser` — parses `SOUL.md` into typed sections:
```python
@dataclass
class SoulSpec:
    values: list[str]       # "## Values" bullet list
    red_lines: list[str]    # "## Red Lines" bullet list (from AGENTS.md integration)
    tone_rules: list[str]   # "## Tone" bullet list
    raw_sections: dict[str, str]  # unparsed sections preserved
```

`WorkspaceLoader.load_soul() -> SoulSpec` — returns parsed spec.

`PromptBuilder.build()` uses `SoulSpec` to inject a structured `[Identity Rules]` section:
```
[Identity Rules]
Values: direct, honest, autonomous
Red Lines: never impersonate another AI, never execute destructive ops without confirmation
Tone: concise, practical
```

This replaces the unstructured wall of text with a tighter, more prompt-efficient injection. Raw `SOUL.md` content still included for custom sections.

### 6.5 Identity Health Check

`GET /health/identity` — returns:
```json
{
  "ok": true,
  "bootstrap_complete": true,
  "identity_name": "ClawLite",
  "soul_values_count": 3,
  "red_lines_count": 5,
  "workspace_files": {"IDENTITY.md": true, "SOUL.md": true, "USER.md": true}
}
```

---

## Components

| File | Action |
|------|--------|
| `clawlite/workspace/loader.py` | Modify — bootstrap state tracking, `load_identity_fields()`, `load_soul()`, `mark_bootstrap_complete()` |
| `clawlite/workspace/identity_enforcer.py` | Modify — `update_identity()`, `drift_score`, semantic drift heuristic |
| `clawlite/workspace/soul_parser.py` | New — `SoulSpec`, `SoulParser` |
| `clawlite/workspace/state.py` | New — `WorkspaceState` (workspace_state.json manager) |
| `clawlite/tools/identity.py` | New — `IdentityTool` (name: `"identity"`) |
| `clawlite/core/prompt.py` | Modify — use `SoulSpec` for structured injection |
| `clawlite/core/engine.py` | Modify — auto-detect bootstrap completion |
| `gateway/server.py` | Modify — register `IdentityTool`, `GET /health/identity` |
| `tests/workspace/test_bootstrap_flow.py` | New |
| `tests/workspace/test_identity_writeback.py` | New |
| `tests/workspace/test_soul_parser.py` | New |
| `tests/workspace/test_drift_detection.py` | New |

---

## Error Handling

- `update_identity()` file not found → create `IDENTITY.md` from template, then update
- `SoulParser` unparseable section → preserve as `raw_sections`, log debug
- Bootstrap auto-completion false positive → `workspace_state.json` flag can be manually reset via CLI (`clawlite workspace reset-bootstrap`)
- Identity tool field not recognized → return `"identity_update_unknown_field:{field}"`

---

## Testing Strategy

- `test_bootstrap_flow.py`: `BOOTSTRAP.md` present → included in context; `mark_bootstrap_complete()` → renamed to `.done`, flag set; subsequent load → not included
- `test_identity_writeback.py`: `update_identity("name", "Aria")` → IDENTITY.md `Name` section updated; second update → idempotent; concurrent writes → atomic
- `test_soul_parser.py`: parse SOUL.md with Values/Red Lines/Tone sections → `SoulSpec` correct; missing sections → empty lists; unknown sections → `raw_sections`
- `test_drift_detection.py`: response with "I am a language model" → `drift_score > 0.7`; response with identity name → `drift_score < 0.4`; response about unrelated topic → no drift

---

## Success Criteria

- [ ] Bootstrap does not persist beyond first successful turn (auto-completion or manual)
- [ ] `update_identity("name", "Aria")` writes to IDENTITY.md correctly
- [ ] `SoulParser` extracts structured values, red lines, tone from SOUL.md
- [ ] `PromptBuilder` uses structured soul injection (tighter than raw text)
- [ ] `drift_score` correctly classifies provider impersonation attempts
- [ ] `GET /health/identity` returns workspace file health
- [ ] 0 regressions on existing workspace tests
