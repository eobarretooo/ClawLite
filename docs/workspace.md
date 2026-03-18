# Workspace

The workspace is the human-facing part of ClawLite. It stores identity, user context, operating rules, heartbeat instructions, and bootstrap notes.

Default path:

- `~/.clawlite/workspace`

Override:

- `CLAWLITE_WORKSPACE=/path/to/workspace`

## Files Created by Onboarding

`clawlite configure --flow quickstart`, `clawlite configure --flow advanced`, and `clawlite onboard` bootstrap these files:

- `IDENTITY.md`
- `SOUL.md`
- `USER.md`
- `AGENTS.md`
- `TOOLS.md`
- `HEARTBEAT.md`
- `BOOTSTRAP.md`
- `memory/MEMORY.md`

Example layout:

```text
~/.clawlite/workspace/
|- IDENTITY.md
|- SOUL.md
|- USER.md
|- AGENTS.md
|- TOOLS.md
|- HEARTBEAT.md
|- BOOTSTRAP.md
`- memory/
   `- MEMORY.md
```

## Runtime-Critical Files

These three files are treated as runtime-critical:

- `IDENTITY.md`
- `SOUL.md`
- `USER.md`

On startup, `WorkspaceLoader.ensure_runtime_files()` checks them for:

- missing files
- empty files
- unreadable files
- corrupt UTF-8 or embedded NUL bytes

If one of them is broken, ClawLite restores it from the built-in template and, when possible, creates a `.bak` backup of the previous file.

## How the Workspace Is Loaded

Prompt building is workspace-first.

The runtime reads these files into the raw system prompt in this order:

1. `IDENTITY.md`
2. `SOUL.md`
3. `AGENTS.md`
4. `TOOLS.md`
5. `HEARTBEAT.md` if heartbeat context is enabled
6. `BOOTSTRAP.md` only while bootstrap is still pending

`USER.md` is parsed separately into a structured user-profile hint, so the assistant can adapt to timezone, language, preferences, and working style without leaking raw placeholder text into the live system prompt.
Legacy defaults such as `Owner` or `(optional)` are ignored at runtime.

### Red Lines

The "Red Lines" section at the top of AGENTS.md is re-injected at the start of every context compaction event. This ensures the agent never loses its core constraints even after the context window is compressed. Keep your most critical rules in the Red Lines section.

## Bootstrap Lifecycle

`BOOTSTRAP.md` is a one-shot file.

Current behavior in code:

- On startup, the gateway bootstraps the workspace if files are missing.
- If `BOOTSTRAP.md` still exists and has content, ClawLite treats bootstrap as pending.
- The runtime tracks bootstrap state in `workspace/memory/bootstrap-state.json`.
- The gateway runs a startup bootstrap cycle using the internal session ID `bootstrap:system`.
- After successful completion, ClawLite records the result and removes `BOOTSTRAP.md` from the workspace.

Useful status surfaces:

- `clawlite status` shows `bootstrap_pending` and `bootstrap_last_status`
- `clawlite diagnostics` includes local bootstrap info
- `/v1/diagnostics` includes the persisted bootstrap state

## Commands You Will Actually Use

Generate the workspace files:

```bash
clawlite onboard
```

Generate or repair missing files:

```bash
clawlite validate onboarding --fix
```

Run the full setup wizard:

```bash
clawlite configure --flow quickstart
clawlite configure --flow advanced
```

## Editing Guidance

The workspace is meant to be edited.

- Use `IDENTITY.md` for who the assistant is. Fill it during the first real conversation — include your name, vibe, emoji, purpose, and communication style. The file guides self-discovery rather than forcing {{placeholders}}.
- Use `SOUL.md` for stable behavior and tone.
- Use `USER.md` for the user's preferences and context. Leave unknown fields blank instead of writing placeholders.
- Use `AGENTS.md` and `TOOLS.md` for repo-local or workspace-local operating rules. Remember that the Red Lines section is automatically re-injected after context compaction.
- Use `HEARTBEAT.md` for periodic behavior.
- Use `memory/MEMORY.md` for durable human-written notes that should stay close to the workspace.

## What Is Not in the Workspace

The workspace is not the same as state or long-term structured memory.

- Session logs live under `~/.clawlite/state/sessions/` by default.
- Structured memory data lives under `~/.clawlite/memory/` by default.
- Provider auth lives in config and, for Codex, optionally in `~/.codex/auth.json`.

For the structured memory layout, see `docs/memory.md`.
