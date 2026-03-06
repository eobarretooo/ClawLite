---
name: gh-issues
description: GitHub issue workflow helper bound to `gh issue` for fast issue listing, triage, and issue-to-PR orchestration.
always: false
metadata: {"clawlite":{"emoji":"🐙","requires":{"bins":["gh","git"]},"auth":{"optionalEnv":["GH_TOKEN"]}}}
command: gh issue
---

# gh-issues

Command-bound skill for GitHub issue operations through `gh issue ...`.

## Auth expectations

- Primary path: authenticated `gh` CLI session (`gh auth status`).
- Optional path: `GH_TOKEN` in environment for headless/auth bootstrap flows.
- If auth fails, stop early and fix credentials before spawning implementation sessions.

## Quick usage

```bash
gh issue list --repo owner/repo --state open --limit 20
gh issue view 123 --repo owner/repo
gh issue comment 123 --repo owner/repo --body "Working on this"
```

## Orchestration workflow (issue -> fix -> PR)

1. Discover and prioritize issues with `gh issue list` filters (`--label`, `--assignee`, `--search`).
2. Spawn workers via `sessions_spawn`/`subagents` (one issue per worker, explicit branch naming and test expectations).
3. Track worker progress with `session_status`; inspect outcomes with `sessions_history`.
4. Validate edits/tests locally via `process`, apply final deltas with `apply_patch` when needed.
5. Open or update PRs with `gh pr create` and post issue linkage (`Fixes #<n>`).

## Safety notes

- Require explicit approval for destructive git actions (force push, history rewrite, branch deletion).
- Keep edits scoped to each issue branch; avoid mixing unrelated fixes.
