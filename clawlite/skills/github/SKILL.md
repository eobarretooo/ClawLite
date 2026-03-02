---
name: github
description: Interact with GitHub using gh CLI for PRs, issues, runs and API queries.
always: false
metadata: {"clawlite":{"emoji":"🐙","requires":{"bins":["gh"]}}}
command: gh
---

# GitHub

Use this skill for repository operations with `gh`.

## Common flows

Check PR status:
```bash
gh pr checks <pr-number> --repo owner/repo
```

List workflow runs:
```bash
gh run list --repo owner/repo --limit 10
```

Inspect failed logs:
```bash
gh run view <run-id> --repo owner/repo --log-failed
```

Structured output:
```bash
gh issue list --repo owner/repo --json number,title --jq '.[] | "#\(.number) \(.title)"'
```

Always use `--repo owner/repo` when outside the repository directory.
