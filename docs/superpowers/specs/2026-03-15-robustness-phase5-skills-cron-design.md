# Robustness Phase 5 — skills + cron

**Goal:** Skills startup validation, dependency graph, versioned contracts. Cron job categories, missed-job policy, and job chaining.

**References:** `clawlite/core/skills.py`, `clawlite/tools/skill.py`, `clawlite/scheduler/cron.py`

---

## Architecture

### skills

#### 5.1 Startup Validation

Current: skill contract issues are detected lazily (only when agent tries to run the skill). Missing dependencies are only discovered at execution time.

Change: `SkillsLoader.validate_all()` — called at gateway startup. For each skill:
1. Checks `SKILL.md` contract fields (existing logic)
2. Checks that required env vars exist (not just non-empty — also checks format where knowable)
3. Checks that `execution_argv[0]` binary is on PATH (for `command` kind skills)
4. Logs a startup summary: `"N skills ready, M unavailable: [names]"`

Does not block startup. Unavailable skills remain registered but `available=False`.

#### 5.2 Dependency Graph

New `SKILL.md` optional field: `requires: ["github", "web-search"]` — list of skill names this skill depends on.

`SkillSpec` gains `requires: list[str]`.

`SkillsLoader` builds a dependency graph on load. `SkillsLoader.get(name)` returns `available=False` if any dependency is unavailable. Error detail: `"skill_unavailable_dependency:{dep_name}"`.

`SkillsLoader.dependency_order()` returns skills in topological order for display/docs.

#### 5.3 Versioned Skill Contracts

`SKILL.md` gains optional `version: "1.0.0"` field. `SkillSpec.version: str`.

`run_skill` tool: if skill version changes between runs, emits a warning log and bus event `skills.version_changed`. Detection: `SkillsLoader` maintains an in-memory dict `_version_snapshot: dict[str, str]` populated at startup (`{skill_name: version_string}`). On each `run_skill` call, compare `spec.version` against `_version_snapshot[name]`. If different (or snapshot entry missing), emit event and update snapshot. Hash is the version string itself — no content hashing needed since `SKILL.md` is reloaded only at startup.

`clawlite skills list` updated to show version column.

---

### cron

#### 5.4 Job Categories

`CronJob` gains `category: str = "user"`. Values: `"user"` (created by agent/user), `"system"` (created by runtime — heartbeat, autonomy).

`CronEngine.list_jobs(category=None)` filters by category. System jobs are hidden from `clawlite cron list` by default (shown with `--all` flag).

`add_job()` gains `category` param.

#### 5.5 Missed-Job Policy

`CronSchedule` gains `missed_policy: Literal["skip", "run_once", "catchup"] = "skip"`.

- `skip` (current behavior): if a job's `next_run_iso` is in the past, run it once and advance schedule normally
- `run_once`: same as skip but emit a `cron.missed_job` bus event
- `catchup`: if missed N runs, run all N (bounded by `catchup_max: int = 3` to prevent storms)

Detected in `_loop()` when `next_run <= now` and `last_run_iso` shows a gap larger than the schedule interval.

#### 5.6 Job Chaining

`CronPayload` gains `on_success_job_id: str = ""` and `on_failure_job_id: str = ""`.

After a job completes:
- If `on_success_job_id` is set and job succeeded → `run_job(on_success_job_id, force=True)`
- If `on_failure_job_id` is set and job failed → `run_job(on_failure_job_id, force=True)`

Chaining is one level deep only (no recursive chains to prevent infinite loops). Chained job runs are logged with `trigger="chain"`.

#### 5.7 Cron Export/Import

`CronEngine.export_jobs() -> list[dict]` — serializes all jobs to JSON-serializable dicts (excluding runtime state like `lease_token`).

`CronEngine.import_jobs(jobs: list[dict], *, overwrite=False)` — restores from export. Useful for backup and migration.

CLI: `clawlite cron export > cron_backup.json`, `clawlite cron import cron_backup.json`.

---

## Components

| File | Action |
|------|--------|
| `clawlite/core/skills.py` | Modify — `validate_all()`, dependency graph, `SkillSpec.requires`, `SkillSpec.version` |
| `clawlite/tools/skill.py` | Modify — dependency check in `run()`, version change detection |
| `clawlite/scheduler/cron.py` | Modify — `category`, `missed_policy`, `catchup`, chaining, export/import |
| `clawlite/scheduler/types.py` | Modify — update `CronJob`, `CronSchedule`, `CronPayload` dataclasses |
| `clawlite/cli/commands.py` | Modify — `skills list` version column, `cron export/import`, `cron list --all` |
| `tests/core/test_skills_validation.py` | New |
| `tests/core/test_skills_deps.py` | New |
| `tests/scheduler/test_cron_categories.py` | New |
| `tests/scheduler/test_cron_missed_policy.py` | New |
| `tests/scheduler/test_cron_chaining.py` | New |
| `tests/scheduler/test_cron_export_import.py` | New |

---

## Error Handling

- Dependency cycle in skills graph → log error at startup, mark all cyclic skills `available=False`
- Catchup max exceeded → run `catchup_max` times, log `cron.catchup_truncated` warning
- Chain job not found → log error, continue (do not fail original job)
- Export with active lease → export includes `lease_token=""` (cleared for safety)

---

## Testing Strategy

- `test_skills_validation.py`: skill with missing binary → `available=False` after `validate_all()`; skill with all deps present → `available=True`
- `test_skills_deps.py`: skill B requires A; A unavailable → B unavailable; A available → B available; circular dep A→B→A → both unavailable
- `test_cron_categories.py`: `add_job(category="system")`, `list_jobs()` hides it, `list_jobs(category="system")` shows it
- `test_cron_missed_policy.py`: job with `run_once` policy missed → `cron.missed_job` bus event; `catchup` policy missed 5 times → only 3 runs
- `test_cron_chaining.py`: job A with `on_success_job_id=B`; A succeeds → B runs; A fails → B doesn't run; B has `on_success_job_id=C` → C doesn't run (no recursion)
- `test_cron_export_import.py`: export N jobs, new engine, import, assert jobs equal (excluding runtime fields)

---

## Success Criteria

- [ ] `validate_all()` logs startup summary with ready/unavailable counts
- [ ] Skills with unmet dependencies report `available=False` with clear reason
- [ ] `SKILL.md` version field parsed and shown in `skills list`
- [ ] System cron jobs hidden from default list, shown with `--all`
- [ ] Missed-job catchup runs bounded by `catchup_max`
- [ ] Job chaining works one level deep; no recursive chains possible
- [ ] `cron export/import` round-trips all jobs correctly
- [ ] 0 regressions on existing scheduler and skills tests
