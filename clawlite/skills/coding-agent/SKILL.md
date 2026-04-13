---
name: coding-agent
description: "Orchestrate multi-step coding tasks by spawning focused ClawLite sessions and subagents, coordinating parallel work, and integrating results with patch tooling. Use when implementing features across multiple files, running parallel refactors, or automating issue-to-PR workflows."
always: false
metadata: {"clawlite":{"emoji":"🧩"}}
script: coding_agent
---

# Coding Agent

Delegate and coordinate coding tasks across spawned sessions and subagents for multi-file features, refactors, migrations, and bugfixes.

## When to Use

- Multi-file features, refactors, or migrations that benefit from isolated workers.
- Parallel tasks requiring progress tracking and explicit integration.
- Issue-to-PR workflows where each unit should run in its own session.

## Workflow

1. **Scope definition**: Define acceptance criteria, touched file paths, and constraints before spawning any work.
2. **Spawn workers**: Use `sessions_spawn` to create one focused worker per independent task. Set explicit timeouts and cleanup policies.
3. **Track progress**: Poll `session_status` to monitor lifecycle, progress, and failure states.
4. **Collect outputs**: Use `sessions_history` to inspect outputs and artifacts before integration.
5. **Integrate**: Apply patches incrementally with `apply_patch`, then run validation commands via `process`.
6. **Summarize**: Report changed files, test results, and open risks to the user.

## Core Tools

| Tool | Purpose |
|------|---------|
| `sessions_spawn` | Create focused workers with scope, timeout, and cleanup policy |
| `subagents` | Run parallel autonomous tasks when decomposition is stable |
| `session_status` | Monitor worker lifecycle and failure states |
| `sessions_history` | Inspect outputs and artifacts before integrating |
| `process` | Run build, test, and git commands; poll long-running jobs |
| `apply_patch` | Apply deterministic file edits for targeted changes |

## Example

Task: "Refactor the auth module and update all callers"

1. Scope: `clawlite/auth/`, callers in `clawlite/gateway/`, `clawlite/cli/`. Acceptance: tests pass.
2. Spawn worker A: refactor `auth/` module internals. Spawn worker B: update gateway callers. Spawn worker C: update CLI callers.
3. Track each worker via `session_status` until complete.
4. Collect patches from `sessions_history`, apply incrementally.
5. Run `python -m pytest tests/ -q --tb=short` to validate.
6. Summarize changes and any remaining manual steps.

## Safety Constraints

- Do not assume PTY or interactive terminal capabilities.
- Prefer non-interactive commands and deterministic arguments.
- Require explicit user approval for destructive actions (hard reset, force push, mass delete, irreversible migrations).
- Maintain branch/repo hygiene: avoid unrelated edits, never discard user work, report blocked operations clearly.
