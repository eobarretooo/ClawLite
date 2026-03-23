# CLI

ClawLite ships with a single CLI entry point: `clawlite`.

Most commands print JSON to stdout. By default, ClawLite reads `~/.clawlite/config.json`. Use `--config <path>` before the subcommand to point to a different JSON or YAML config file.

## Global Flags

| Flag | What it does | Example |
| --- | --- | --- |
| `--config <path>` | Uses a non-default config file | `clawlite --config ./config.dev.json status` |
| `--profile <name>` | Applies `config.<profile>.json|yaml` as an overlay on top of `--config` | `clawlite --config ./config.yaml --profile prod status` |
| `--version` | Prints the installed version | `clawlite --version` |

The module entry point is also available as `python -m clawlite.cli`.

Profile precedence is: base config file → `config.<profile>.json|yaml` overlay → environment variables.

## Runtime Commands

| Command | What it does | Example |
| --- | --- | --- |
| `start` | Starts the FastAPI gateway | `clawlite start --host 127.0.0.1 --port 8787` |
| `gateway` | Alias of `start` | `clawlite gateway --port 8787` |
| `run <prompt>` | Runs one prompt directly through the engine | `clawlite run "summarize this repo" --session-id cli:test --timeout 30` |
| `hatch` | Runs the dedicated first-run bootstrap hatch session | `clawlite hatch --message "Wake up, my friend!"` |
| `status` | Prints a local config/runtime summary | `clawlite status` |
| `dashboard` | Opens or prints the local dashboard handoff | `clawlite dashboard --no-open` |
| `discord` | Discord operator control commands | `clawlite discord status` |
| `telegram` | Telegram operator control commands | `clawlite telegram status` |
| `jobs` | Inspects or cancels persisted background jobs | `clawlite jobs list` |
| `provider recover` | Clears provider failover suppression/cooldown through the gateway | `clawlite provider recover --role primary` |
| `supervisor recover` | Triggers runtime supervisor recovery through the gateway | `clawlite supervisor recover --component heartbeat` |
| `autonomy wake` | Triggers a manual autonomy wake through the gateway | `clawlite autonomy wake --kind proactive` |

Notes:

- `run` does not require the gateway to be running.
- `hatch` does not require the gateway to be running; it uses the dedicated `hatch:operator` session and only completes bootstrap when a pending hatch exists.
- `status` includes enabled channels, provider model, heartbeat interval, and bootstrap state.
- `dashboard` prints the current dashboard URL, a short-lived one-time dashboard handoff URL, bootstrap state, post-onboarding guidance (including web-search hints), and can open the browser unless `--no-open` is passed. The browser uses that handoff only for the initial exchange, then keeps only the derived dashboard session in the current tab after bootstrap.
- `discord status` reads Discord runtime state from `/api/dashboard/state`; `discord refresh` calls the live gateway transport-refresh control.
- `telegram status` reads Telegram runtime state from `/api/dashboard/state` and includes operator hints; `telegram refresh`, `telegram offset-commit`, `telegram offset-sync`, and `telegram offset-reset` call the live gateway control endpoints.
- `jobs list` reads from the persisted job store, `jobs status` inspects one job by id, and `jobs cancel` requires a live runtime because it calls the gateway cancellation path.
- `provider recover` calls the live gateway provider recovery control and is intended for failover suppression/cooldown recovery after auth/quota/config issues are fixed.
- `supervisor recover` calls the live gateway supervisor recovery control and can target one component or all tracked components.
- `autonomy wake` triggers the live autonomy wake control and is intended for manual proactive/autonomy nudges when an operator wants to run the loop immediately.

## Setup and Onboarding

| Command | What it does | Example |
| --- | --- | --- |
| `configure --flow quickstart` | Compatibility shortcut to the guided onboarding wizard | `clawlite configure --flow quickstart` |
| `configure --flow advanced` | Compatibility shortcut to the advanced onboarding wizard | `clawlite configure --flow advanced` |
| `onboard` | Generates workspace template files without running the wizard | `clawlite onboard --assistant-name ClawLite --user-name Renan` |
| `onboard --wizard` | Runs the onboarding wizard from `onboard` | `clawlite onboard --wizard --flow advanced --overwrite` |

Identity and user flags accepted by `onboard`:

- `--assistant-name`
- `--assistant-emoji`
- `--assistant-creature`
- `--assistant-vibe`
- `--assistant-backstory`
- `--user-name`
- `--user-timezone`
- `--user-context`
- `--user-preferences`
- `--overwrite`

`configure --flow ...` is a compatibility shortcut to `onboard --wizard --flow ...`. Plain `configure` opens the newer two-level Basic / Advanced configuration menu.

## Validation Commands

| Command | What it does | Example |
| --- | --- | --- |
| `validate provider` | Validates the active provider/model config | `clawlite validate provider` |
| `validate channels` | Validates enabled channel config | `clawlite validate channels` |
| `validate onboarding` | Checks workspace bootstrap files | `clawlite validate onboarding` |
| `validate onboarding --fix` | Creates missing workspace files | `clawlite validate onboarding --fix` |
| `validate config` | Runs strict config-key validation | `clawlite validate config` |
| `validate preflight` | Runs local checks plus optional live probes | `clawlite validate preflight --gateway-url http://127.0.0.1:8787` |
| `validate preflight --docker` | Also validates Docker/Compose readiness and current gateway container state; requires `docker` + Compose v2 on the local machine | `clawlite validate preflight --docker` |

Useful `validate preflight` flags:

- `--gateway-url <url>`
- `--token <bearer-token>`
- `--timeout <seconds>`
- `--docker`
- `--provider-live`
- `--telegram-live`

Current built-in `validate channels` checks:

- Telegram: requires `token`, warns if `allow_from` is empty.
- Discord: requires `token`.
- Slack: requires `bot_token`; `app_token` is needed for inbound Socket Mode.
- WhatsApp: requires `bridge_url`; inbound webhook also needs `webhook_secret`.
- IRC: requires `host`, `port`, and `channels_to_join`.
- Extra placeholder channels have no deep static validation rules.

## Provider Commands

| Command | What it does | Example |
| --- | --- | --- |
| `provider login <oauth-provider>` | Persists OAuth credentials for `openai-codex`, `gemini-oauth`, or `qwen-oauth` | `clawlite provider login gemini-oauth` |
| `provider status [provider]` | Shows auth/status for one provider | `clawlite provider status openai` |
| `provider logout [provider]` | Clears persisted OAuth credentials for one OAuth provider | `clawlite provider logout gemini-oauth` |
| `provider use <provider> --model <model>` | Persists the active provider/model | `clawlite provider use openai --model openai/gpt-4o-mini` |
| `provider set-auth <provider> --api-key <key>` | Persists API-key auth for non-OAuth providers | `clawlite provider set-auth openrouter --api-key sk-or-...` |
| `provider clear-auth <provider>` | Clears API-key auth and optional base URL | `clawlite provider clear-auth openrouter --clear-api-base` |

Useful flags:

- `provider login openai-codex|gemini-oauth|qwen-oauth`: `--access-token`, `--account-id`, `--keep-model`, `--set-model`, `--no-interactive`
- `provider use`: `--fallback-model`, `--clear-fallback`
- `provider set-auth`: `--api-base`, `--header key=value`, `--clear-headers`, `--clear-api-base`
- `provider clear-auth`: `--clear-api-base`

Notes:

- `provider login` and `provider logout` support `openai-codex`, `gemini-oauth`, and `qwen-oauth`.
- `provider set-auth` is the easiest way to seed providers that need custom `api_base`, such as `azure-openai`, or newly added gateways such as `aihubmix`, `siliconflow`, and `cerebras`.
- `--set-model` is a deprecated compatibility flag; Codex login already switches to the default Codex model unless you pass `--keep-model`.
- `provider status` defaults to `openai-codex` when no provider is supplied.
- Provider aliases such as `codex`, `google`, `claude`, `hf`, and `kimi` are accepted where supported by the registry.

## Control and Diagnostics

| Command | What it does | Example |
| --- | --- | --- |
| `heartbeat trigger` | Calls `/v1/control/heartbeat/trigger` on the gateway | `clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787` |
| `pairing list <channel>` | Lists pending pairing requests | `clawlite pairing list telegram` |
| `pairing approve <channel> <code>` | Approves a pending pairing code | `clawlite pairing approve telegram ABC123` |
| `diagnostics` | Prints local diagnostics and optional gateway probes | `clawlite diagnostics --gateway-url http://127.0.0.1:8787` |

Useful flags:

- `heartbeat trigger`: `--gateway-url`, `--token`, `--timeout`
- `diagnostics`: `--gateway-url`, `--token`, `--timeout`, `--no-validation`

Notes:

- Pairing is only meaningful for Telegram today.
- `diagnostics` can probe `/health`, `/v1/status`, and `/v1/diagnostics` when a gateway URL is provided.

## Memory Commands

The bare `memory` command prints an overview. Everything else hangs off `clawlite memory ...`.

| Command | What it does | Example |
| --- | --- | --- |
| `memory` | Prints the overview snapshot | `clawlite memory` |
| `memory doctor` | Emits a diagnostics snapshot | `clawlite memory doctor` |
| `memory doctor --repair` | Runs a safe repair pass before reporting | `clawlite memory doctor --repair` |
| `memory eval` | Runs deterministic retrieval evaluation | `clawlite memory eval --limit 10` |
| `memory quality` | Computes and persists memory quality state | `clawlite memory quality --gateway-url http://127.0.0.1:8787` |
| `memory profile` | Prints the profile snapshot | `clawlite memory profile` |
| `memory suggest` | Prints proactive memory suggestions | `clawlite memory suggest` |
| `memory suggest --no-refresh` | Reads pending suggestions without scanning again | `clawlite memory suggest --no-refresh` |
| `memory snapshot` | Creates a versioned snapshot | `clawlite memory snapshot --tag before-upgrade` |
| `memory version` | Lists available snapshot IDs | `clawlite memory version` |
| `memory rollback <id>` | Rolls memory back to a snapshot | `clawlite memory rollback 20260308-main-before-upgrade` |
| `memory privacy` | Prints the privacy rules snapshot | `clawlite memory privacy` |
| `memory export` | Exports memory state | `clawlite memory export --out ./memory-export.json` |
| `memory import <file>` | Imports memory from a file | `clawlite memory import ./memory-export.json` |
| `memory branches` | Prints branch metadata | `clawlite memory branches` |
| `memory branch <name>` | Creates a branch | `clawlite memory branch experiment --checkout` |
| `memory checkout <name>` | Switches the active branch | `clawlite memory checkout main` |
| `memory merge --source <name> --target <name>` | Merges one branch into another | `clawlite memory merge --source experiment --target main --tag merge` |
| `memory share-optin --user <user> --enabled true|false` | Toggles shared-memory opt-in for one user | `clawlite memory share-optin --user alice --enabled true` |

Useful flags:

- `memory doctor`: `--json`, `--repair`
- `memory quality`: `--json`, `--limit`, `--gateway-url`, `--token`, `--timeout`
- `memory snapshot`: `--tag`
- `memory export`: `--out`
- `memory branch`: `--from-version`, `--checkout`
- `memory merge`: `--source`, `--target`, `--tag`

Notes:

- `memory doctor` and `memory quality` already emit JSON even without `--json`.
- `share-optin --enabled` accepts `true|false`, `yes|no`, or `1|0`.

## Cron Commands

| Command | What it does | Example |
| --- | --- | --- |
| `cron add` | Adds a scheduled job | `clawlite cron add --session-id ops --expression "every 120" --prompt "check alerts"` |
| `cron list` | Lists jobs for a session | `clawlite cron list --session-id ops` |
| `cron remove` | Removes a job by ID | `clawlite cron remove --job-id job_123` |
| `cron enable <job_id>` | Enables a job | `clawlite cron enable job_123` |
| `cron disable <job_id>` | Disables a job | `clawlite cron disable job_123` |
| `cron run <job_id>` | Runs a job immediately | `clawlite cron run job_123` |

`cron add --expression` accepts three forms:

- `every 120`
- `at 2026-03-02T20:00:00`
- standard cron syntax such as `0 9 * * *` (requires `croniter`)

## Skills Commands

| Command | What it does | Example |
| --- | --- | --- |
| `skills list` | Lists discovered skills | `clawlite skills list` |
| `skills list --all` | Includes unavailable skills | `clawlite skills list --all` |
| `skills show <name>` | Prints one skill body and metadata | `clawlite skills show summarize` |
| `skills check` | Emits the aggregated diagnostics report | `clawlite skills check` |
| `skills refresh` | Triggers live runtime skill discovery refresh through the gateway | `clawlite skills refresh --gateway-url http://127.0.0.1:8787` |
| `skills doctor` | Turns diagnostics into actionable remediation hints, with optional status/source/query filters | `clawlite skills doctor --status missing_requirements --source builtin --query github` |
| `skills validate` | Refreshes live discovery and returns the current actionable blocked-skills summary through the gateway | `clawlite skills validate --status missing_requirements --query github` |
| `skills config <name>` | Shows or updates `skills.entries.<skillKey>` for one skill in the active config/profile | `clawlite skills config github --api-key ghp_example --env GH_HOST=github.example.com --enable` |
| `skills enable <name>` | Enables a skill in local state | `clawlite skills enable github` |
| `skills disable <name>` | Disables a skill in local state | `clawlite skills disable github` |
| `skills pin <name>` | Pins a skill in local state | `clawlite skills pin summarize` |
| `skills unpin <name>` | Unpins a skill in local state | `clawlite skills unpin summarize` |
| `skills pin-version <name> <version>` | Locks a skill to a specific version string | `clawlite skills pin-version github 2026.03` |
| `skills clear-version <name>` | Removes the local version pin for a skill | `clawlite skills clear-version github` |
| `skills search <query>` | Searches ClawHub for managed skills and reports matching local managed skills | `clawlite skills search "discord moderation"` |
| `skills install <slug>` | Installs a managed skill into `~/.clawlite/marketplace` | `clawlite skills install jira-helper` |
| `skills update <name>` | Updates one managed skill by folder slug or skill name via ClawHub | `clawlite skills update jira-helper` |
| `skills managed` | Lists managed marketplace skills discovered locally, with optional status/query filters and aggregate `status_counts` | `clawlite skills managed --status missing_requirements --query jira` |
| `skills sync` | Updates all managed marketplace skills via ClawHub | `clawlite skills sync` |
| `skills remove <name>` | Removes one managed marketplace skill | `clawlite skills remove jira-helper` |

Skill discovery includes:

- built-in skills under `clawlite/skills`
- workspace skills under `~/.clawlite/workspace/skills`
- marketplace skills under `~/.clawlite/marketplace/skills`

The local skill state is stored in `~/.clawlite/state/skills-state.json`.

`skills managed` includes the managed folder `slug`, resolved runtime `status`, and a hint when the skill is blocked or missing requirements, plus global `status_counts` for the full managed inventory. `skills update` resolves either the slug or the discovered skill name before invoking ClawHub, and successful `install`/`update`/`sync` calls now echo the resolved local marketplace state. `skills search` also includes `local_matches` so an operator can see whether a remote query already exists locally without leaving the CLI. `skills doctor` focuses on broken or blocked skills by default and includes remediation hints for missing env vars, binaries, config keys, invalid contracts, and `skills.allowBundled` policy blocks. `skills config` gives a direct write path for `skills.entries.<skillKey>` in the active base/profile config, so operators can set `apiKey`, merge `env` overrides, or toggle `enabled` without editing raw JSON/YAML. Both `skills doctor` and `skills managed` now accept `--query` for case-insensitive triage by name, skill key, description, requirement, or hint text.
`skills refresh` is the explicit live-control path for runtime discovery. It calls `POST /v1/control/skills/refresh`, returns the refresh outcome plus the current skills/watcher summary, and accepts `--no-force` when you want the runtime debounce policy to decide whether a full refresh is necessary. `skills validate` builds on that same live control plane through `POST /v1/control/skills/validate`: it runs refresh plus the current blocked-skills diagnosis in one step, supports the same `--no-force`, `--all`, `--status`, `--source`, and `--query` filters, and keeps `--config` / `--profile` aligned with the active gateway settings instead of silently falling back to the default config file.

## Tools Commands

| Command | What it does | Example |
| --- | --- | --- |
| `tools safety <tool>` | Previews the effective safety policy for one tool call | `clawlite tools safety browser --session-id telegram:1 --channel telegram --args-json '{"action":"evaluate"}'` |
| `tools approvals` | Lists live pending/reviewed tool approval requests from the gateway, with optional tool/rule filters | `clawlite tools approvals --include-grants --tool browser --rule browser:evaluate` |
| `tools approve <request_id>` | Approves one pending tool request through the gateway | `clawlite tools approve req-1 --note "approved after review"` |
| `tools reject <request_id>` | Rejects one pending tool request through the gateway | `clawlite tools reject req-1 --note "needs safer scope"` |
| `tools revoke-grant` | Revokes active temporary tool grants through the gateway | `clawlite tools revoke-grant --session-id telegram:1 --channel telegram --rule browser:evaluate` |
| `tools catalog` | Fetches the live gateway tool catalog | `clawlite tools catalog --include-schema --group runtime` |
| `tools show <name>` | Shows one live tool entry, resolving aliases like `bash -> exec` | `clawlite tools show bash` |

`tools safety` does not run the tool. It shows the resolved channel, derived specifiers, matched risky rules, matched approval rules, a structured `approval_context`, and a final `decision` of `allow`, `approval`, or `block`. For `exec`, the preview now also exposes derived specifiers such as `exec:shell`, `exec:env-key:...`, and `exec:cwd`.
`tools approvals`, `tools approve`, `tools reject`, and `tools revoke-grant` use the live gateway control surface and accept the same `--gateway-url`, `--token`, and `--timeout` flags as `tools catalog`. Approval rows now surface structured context like exec binary/env keys/cwd and browser or web host targets, and `tools approvals` can narrow the queue further with `--tool` and `--rule`. When a gateway token is configured, the approval/grant endpoints require that token even on loopback. When a request row includes `requester_actor`, that review is actor-bound: inspect it from CLI if you want, but approve/reject it from the original Telegram/Discord interaction instead of the generic CLI command. Generic CLI-triggered reviews are recorded as `control-plane`, not as the optional `--actor` label.
`tools catalog` and `tools show` call the gateway catalog endpoint and accept `--gateway-url`, `--token`, and `--timeout`.

## Common Operator Workflow

Typical first-run flow:

```bash
clawlite configure --flow quickstart
clawlite gateway
clawlite run "hello"
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

Typical provider switch:

```bash
clawlite provider set-auth openai --api-key sk-...
clawlite provider use openai --model openai/gpt-4o-mini
clawlite validate provider
```

Typical memory maintenance:

```bash
clawlite memory doctor
clawlite memory quality --gateway-url http://127.0.0.1:8787
clawlite memory snapshot --tag before-change
```
