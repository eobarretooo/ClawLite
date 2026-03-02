# Skill Port Matrix (Nanobot/OpenClaw -> ClawLite)

This matrix records which skill concepts are ported now versus intentionally skipped based on current ClawLite capabilities.

| Concept | Source | Decision | ClawLite status | Rationale |
|---|---|---|---|---|
| github skill (`gh`) | nanobot + openclaw docs | PORT NOW | `clawlite/skills/github/SKILL.md` | Fully supported via `command: gh` and bin requirement gating. |
| weather skill | nanobot + openclaw docs | PORT NOW | `clawlite/skills/weather/SKILL.md` | Supported by `script: weather` in `run_skill` dispatcher. |
| summarize CLI skill | nanobot + openclaw docs | PORT NOW | `clawlite/skills/summarize/SKILL.md` | Supported via `command: summarize` when binary exists. |
| tmux interactive skill | nanobot + openclaw docs | PORT NOW | `clawlite/skills/tmux/SKILL.md` | Supported via `command: tmux` plus OS/bin requirement gating. |
| clawhub registry skill | nanobot + openclaw docs | PORT NOW | `clawlite/skills/clawhub/SKILL.md` | Supported via `command: npx --yes clawhub@latest`. |
| hub alias skill | existing ClawLite | PORT NOW | `clawlite/skills/hub/SKILL.md` | Kept for backward compatibility while `clawhub` is canonical. |
| cron scheduling skill | nanobot + openclaw docs | PORT NOW | `clawlite/skills/cron/SKILL.md` | Fully supported by `cron` tool actions and params. |
| memory operating skill | nanobot + openclaw docs | PORT NOW | `clawlite/skills/memory/SKILL.md` | Supported with workspace/state files plus file and exec tools. |
| skill-creator meta-skill | nanobot + openclaw docs | PORT NOW | `clawlite/skills/skill-creator/SKILL.md` | Useful daily authoring workflow, aligned to ClawLite parser/contracts. |
| web search helper skill | existing ClawLite + openclaw tools | PORT NOW | `clawlite/skills/web-search/SKILL.md` | Supported by `script: web_search` and `web_fetch` tool usage. |
| `user-invocable` frontmatter | openclaw skill docs | SKIP | Not implemented | ClawLite loader ignores slash-command exposure controls. |
| `disable-model-invocation` frontmatter | openclaw skill docs | SKIP | Not implemented | ClawLite prompt injection has no per-skill suppression flag. |
| `command-dispatch` / `command-tool` / `command-arg-mode` | openclaw skill docs | SKIP | Not implemented | No direct slash-command -> tool bridge in ClawLite skill loader/tooling. |
| `requires.anyBins` and `requires.config` gates | openclaw skill docs | SKIP | Not implemented | ClawLite requirement model supports `bins`, `env`, `os` only. |
| installer metadata (`metadata.*.install`) | openclaw skill docs | SKIP | Not implemented | No installer UI/runtime in ClawLite; metadata is ignored. |
