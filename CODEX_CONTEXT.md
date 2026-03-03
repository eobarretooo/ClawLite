# CODEX_CONTEXT

## Current state (2026-03-02)

- Branch: `main`
- Session focus: repository cleanup and test base standardization
- Tests: `48 passed` with `pytest -q tests`

## Changes applied in this cleanup

1. `tests_next/` renamed to `tests/`.
2. `clawlite/core/__init__.py` created.
3. Removed from version control:
   - stale website artifacts
   - `hub/marketplace/`
   - `scripts/community_pack.py`
   - `scripts/sync_community_downloads.py`
   - `scripts/sync_openclaw_skills.py`
   - `scripts/templates/community/`
4. `clawlite/tools/skill.py` documented with module and class docstrings.
5. `.gitignore` fixed: removed invalid `~/.clawlite/` entry.
6. References updated for the new test directory:
   - `.github/workflows/ci.yml`
   - `docs/OPERATIONS.md`
   - `scripts/smoke_test.sh`

## Technical note: tools/skill.py

- **Required** file for real execution of skills discovered via `SKILL.md`.
- It connects discovery (`SkillsLoader`) with execution (`command:` / `script:`), avoiding manual `registry.py` edits for each new skill.

## Suggested next step

- Review README/documentation to remove references to removed legacy artifacts if they still exist.
