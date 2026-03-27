# Skills

ClawLite uses markdown skills (`SKILL.md`) with automatic discovery.

## Loaded sources

1. Builtin (repo): `clawlite/skills/*/SKILL.md`
2. User workspace: `~/.clawlite/workspace/skills/*/SKILL.md`
3. Marketplace local: `~/.clawlite/marketplace/skills/*/SKILL.md`

## Supported frontmatter fields

- `name`
- `description`
- `always`
- `requires` (legacy, CSV list of binaries)
- `requirements` (new JSON format with `bins`, `env`, `os`)
- `command` / `script` (execution metadata)

`metadata` JSON with `clawlite`/`nanobot`/`openclaw` namespace is also accepted, for example:

```yaml
metadata: {"clawlite":{"requires":{"bins":["gh"],"env":["GITHUB_TOKEN"]},"os":["linux","darwin"]}}
```

OpenClaw-style runtime keys are also recognized inside `metadata.openclaw`, including:

- `primaryEnv`
- `skillKey`
- `requires.bins`
- `requires.env`
- `requires.config`
- `requires.anyBins`

## Duplicate policy

When two skills have the same `name`, resolution is deterministic:

1. `workspace` overrides `marketplace`
2. `marketplace` overrides `builtin`
3. tie in the same source: lower lexicographic path (`path`) wins

## Current built-ins

- `cron`
- `memory`
- `github`
- `summarize`
- `skill-creator`
- `web-search`
- `weather`
- `tmux`
- `hub`
- `clawhub`

## Inspection CLI

```bash
clawlite skills list
clawlite skills list --all
clawlite skills show cron
clawlite skills doctor
clawlite skills doctor --status missing_requirements --source builtin
clawlite skills doctor --query github
clawlite skills refresh
clawlite skills refresh --no-force
clawlite skills validate
clawlite skills validate --no-force --status missing_requirements --query github
clawlite skills config github --api-key ghp_example_token --env GH_HOST=github.example.com --enable
clawlite skills search "discord"
clawlite skills install jira-helper
clawlite skills update jira-helper
clawlite skills managed
clawlite skills managed --status missing_requirements
clawlite skills managed --query jira
clawlite skills sync
clawlite skills remove jira-helper
```

`skills list --all` includes unavailable skills in the current environment and shows missing requirements.
`skills show` and `skills check` also surface the resolved `skill_key` and `primary_env` used for `skills.entries`.
`skills search` now includes `local_matches`, so operators can compare ClawHub search hits against already managed marketplace skills without a second command.
`skills doctor` turns that deterministic diagnostics data into remediation hints, grouped around the actual blocker: missing env vars, binaries, config keys, bundled-skill policy, or invalid `SKILL.md` contract. It also supports `--status`, `--source`, and `--query` when you only want one operational slice, for example builtin skills that are blocked by missing secrets.
`skills config <name>` is the direct config path for `skills.entries.<skillKey>` and can either inspect the current entry or update `apiKey`, `env`, and `enabled` for the active base/profile config without editing JSON or YAML by hand.
`skills managed` shows only the marketplace-local skills currently discovered under `~/.clawlite/marketplace/skills`, including the managed folder `slug`, resolved runtime `status`, description, and remediation hint when a managed skill is blocked or missing requirements. It also supports `--status` and `--query` for filtering to one lifecycle slice such as `ready`, `missing_requirements`, or `jira`, while still returning global `status_counts` for the full managed inventory. The live/CLI managed snapshot now also carries a compact `blockers` drill-down for the currently visible slice, including blocker counts by kind (`env`, `config`, `bin`, `contract`, `policy`, `os`, `unavailable`, or `other`), the top visible blocker detail, a bounded set of example blocked skills, and `visible_blocked_count` so filtered triage can stay distinct from the unfiltered `blocked_count` total.
The packaged dashboard now also reuses that same diagnostics payload in the Knowledge tab, surfacing compact cards for availability, runnable coverage, always-on blockers, missing requirements, contract issues, and watcher health without falling back to the raw JSON preview first.
That dashboard summary now also includes a compact `managed` marketplace lifecycle block, so operators can see how many marketplace skills are tracked, ready, blocked, or disabled plus a bounded preview of the first managed entries without leaving the packaged control-plane.
That same dashboard card now also exposes the first blocked skills with remediation hints plus dedicated first-class controls for `Refresh skills inventory`, `Doctor blocked skills`, and `Validate skills inventory`, backed by the explicit runtime routes `POST /v1/control/skills/refresh`, `POST /v1/control/skills/doctor`, and `POST /v1/control/skills/validate`. The refresh path is also available from CLI via `clawlite skills refresh`, while the doctor/validate payloads now have live control-plane equivalents for dashboard/operator use. Those refresh/doctor/validate paths now reuse the same config-aware loader logic too, so explicit `--config` / `--profile` selection stays aligned across CLI and live runtime diagnosis. `skills validate` is the compact operational path when an operator wants one command or button that both refreshes discovery and returns the actionable blocked-skills report in the same response.
Managed lifecycle now also has a first-class live read path through `GET /v1/control/skills/managed` and `GET /api/skills/managed`, and the packaged dashboard Knowledge tab exposes that via `Inspect managed skills` for an on-demand full inventory snapshot instead of only the bounded diagnostics preview. That live path walks the marketplace tree directly, so it still reports installed marketplace skills even when a workspace override shadows the same discovered skill name. The dashboard control now also accepts `status` and free-text `query` filters before fetch, so operators can inspect only one lifecycle slice such as `missing_requirements` or search for one managed skill without leaving the packaged control plane. That same live slice now includes `blockers` drill-down, and the Knowledge tab renders a dedicated `Managed blockers` summary plus bounded blocker example cards so marketplace triage no longer requires scanning every blocked row manually.
Managed lifecycle now also has a first-class live write path for the safest bulk action: `POST /v1/control/skills/sync` and `POST /api/skills/sync` run the same `clawhub update --all` flow as `clawlite skills sync`, refresh runtime discovery immediately afterward, and return the resulting managed inventory snapshot. The packaged dashboard Knowledge tab exposes that through `Sync managed skills`, so operators can refresh the whole managed marketplace state from the control plane before re-running filtered inspection.

Managed installs use the marketplace root: `~/.clawlite/marketplace/skills`.
`skills update <name>` resolves either the managed folder slug or the discovered skill name before calling `clawhub update <slug>`. Successful `install`, `update`, and `sync` responses now echo the resolved local marketplace state (`managed_count`, `status_counts`, and resolved rows) so operators can see post-action readiness immediately. `skills remove` also returns the removed row plus the remaining managed inventory summary.

## Real skill execution (tool)

Runtime exposes the `run_skill` tool.

Main fields:
- `name` (required)
- `input` or `args`
- `timeout`
- `query` (for `web-search`)
- `location` (for `weather`)

Flow:
1. resolve skill by name
2. validate availability (`bins/env/os`)
3. execute mapped `command` or `script`

If the underlying tool policy requires approval, command-backed or tool-backed skills return `skill_requires_approval:<skill>:...`. On Telegram and Discord, the runtime now surfaces native approve/reject controls for the blocked tool request; after approval, retry the original skill call in the same session.

## Config overrides

ClawLite also reads `skills.entries.<skillKey>` from the active config payload. This follows the same file/profile precedence as the main config loader:

1. base config file
2. `config.<profile>.yaml|json`
3. env vars

Supported fields today:

- `enabled: false` to disable the skill
- `env` to inject per-skill environment variables into `command` skills
- `apiKey` as a convenience for skills that declare `metadata.openclaw.primaryEnv`
- `allowBundled` to restrict builtin skills without affecting workspace or marketplace overrides

Operator shortcut:

```bash
clawlite skills config gh-issues --api-key ghp_example_token --enable
clawlite skills config env-skill --env CUSTOM_TOKEN=secret-value
clawlite skills config gh-issues --clear-api-key
clawlite skills config gh-issues --clear
```

Example:

```yaml
skills:
  allowBundled:
    - gh-issues
  entries:
    gh-issues:
      enabled: true
      apiKey: ghp_example_token
    env-skill:
      env:
        CUSTOM_TOKEN: secret-value
```

Like `openclaw`, injected env keys are only applied when the variable is not already set in the host process.

## Runtime summary format

`render_for_prompt()` uses an XML contract compatible with the skills tool:

```xml
<available_skills>
<skill>
<name>github</name>
<description>Interact with GitHub using gh CLI for PRs, issues, runs and API queries.</description>
<location>/path/to/SKILL.md</location>
</skill>
</available_skills>
```

## Progressive Loading

`SkillsLoader.build_skills_summary()` returns a compact XML summary of all skills (name + description only) for injection into the agent context. This avoids bloating the prompt with full skill content.

Use `load_skill_full(name)` to fetch the complete `SKILL.md` content on demand when the agent needs to execute a specific skill.
