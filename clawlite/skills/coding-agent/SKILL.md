---
name: coding-agent
description: Orchestrate coding work with ClawLite sessions/subagents and patch tooling for multi-step implementation flows.
always: false
metadata: {"clawlite":{"emoji":"🧩"}}
---

# Coding Agent

Guide-only skill for delegating code tasks to spawned sessions/subagents and coordinating completion.

## When to use

- Multi-file features, refactors, migrations, and bugfixes that benefit from isolated workers.
- Parallel tasks that need progress tracking and explicit integration.
- Issue-to-PR workflows where each unit should run in its own session.

## Core tools

- `sessions_spawn`: create focused workers with clear scope, timeout, and cleanup policy.
- `subagents`: run parallel autonomous tasks when decomposition is stable.
- `session_status`: monitor worker lifecycle, progress, and failure states.
- `sessions_history`: inspect outputs/artifacts before integrating.
- `process`: run build/test/git commands and poll long-running jobs.
- `apply_patch`: apply deterministic file edits for targeted changes.

## Operating pattern

1. Define scope, acceptance checks, and touched paths before spawning work.
2. Spawn one worker per independent task with explicit constraints.
3. Track status and collect outputs; rerun failed workers with narrowed prompts.
4. Integrate patches incrementally, then run local validation commands.
5. Prepare final summary with changed files, checks, and open risks.

## Safety constraints

- Do not assume PTY or interactive terminal capabilities for skill execution.
- Prefer non-interactive commands and deterministic arguments.
- Require explicit user approval for destructive actions (`rm`, hard reset, force push, mass delete, irreversible migrations).
- Keep branch/repo hygiene: avoid unrelated edits, never discard user work, and report blocked operations clearly.
