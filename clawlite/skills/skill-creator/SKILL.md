---
name: skill-creator
description: "Create or update SKILL.md packages with deterministic frontmatter, clear trigger descriptions, and valid command/script execution mappings. Use when the user wants to build a new skill, improve an existing skill definition, or troubleshoot skill loading issues."
always: false
metadata: {"clawlite":{"emoji":"🛠️"}}
---

# Skill Creator

Create or improve ClawLite skills in `clawlite/skills/` or `~/.clawlite/workspace/skills/`.

## Workflow

1. **Choose location**: Project skills go in `clawlite/skills/<skill-name>/SKILL.md`. User-level skills go in `~/.clawlite/workspace/skills/<skill-name>/SKILL.md`.
2. **Write frontmatter**: Follow the deterministic schema below — every field must be valid.
3. **Write body**: Add trigger description, workflow steps, examples, and safety notes.
4. **Validate**: Confirm tool/script names exist in ClawLite, file references resolve, and metadata parses as JSON.

## Frontmatter Schema

```yaml
---
name: kebab-case-name          # Required. Must match directory name.
description: "One-line summary ending with a 'Use when...' clause."  # Required. Quoted string.
always: false                   # Optional. true = runs on every prompt.
homepage: https://example.com   # Optional. Link to external docs.
metadata: {"clawlite":{"emoji":"🔧"}}  # Optional. Single-line JSON.
script: tool_name               # Use ONE of: script OR command.
command: npx some-cli           # script = internal tool, command = shell.
---
```

## Frontmatter Rules

- `name`: kebab-case, must match the skill's directory name.
- `description`: Quoted string (not chevron `>`). End with a "Use when..." clause for trigger matching.
- `metadata`: Single-line JSON only (`metadata: {"clawlite":{...}}`). Put binary/OS requirements in `metadata.clawlite.requires` and `metadata.clawlite.os`.
- Execution: Include exactly one of `script` (for ClawLite tool dispatch) or `command` (for shell execution). Never both.

## Example

Creating a skill for Slack notifications:

```yaml
---
name: slack-notify
description: "Send messages and thread replies to Slack channels via webhook. Use when the user wants to post updates or alerts to Slack."
always: false
metadata: {"clawlite":{"emoji":"💬","requires":{"env":["SLACK_WEBHOOK_URL"]}}}
script: slack_notify
---
```

Body includes: trigger description, workflow steps, payload format, and error handling notes.

## Validation Checklist

- [ ] `name` is kebab-case and matches directory name
- [ ] `description` is a quoted string with "Use when..." clause
- [ ] `metadata` is valid single-line JSON
- [ ] `script` or `command` references an existing tool/binary
- [ ] Body has clear trigger, workflow, and at least one example
