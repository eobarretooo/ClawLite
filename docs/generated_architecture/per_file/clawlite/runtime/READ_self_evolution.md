# READ clawlite/runtime/self_evolution.py

## Identity

- Path: `clawlite/runtime/self_evolution.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 1282
- Size bytes: 51749
- SHA1: `84fc263a9b80fd225bf4d8736f705e1601050f92`

## Summary

`clawlite.runtime.self_evolution` is a Python module in the `runtime` area. It defines 11 class(es), led by `EvolutionLog`, `EvolutionRecord`, `FixProposal`, `FixProposer`. It exposes 43 function(s), including `__init__`, `_approval_metadata`, `_build_prompt`, `_call`, `_do_run`, `_notify_operator`. It depends on 16 import statement target(s).

## Structural Data

- Classes: 11
- Functions: 37
- Async functions: 6
- Constants: 12
- Internal imports: 1
- Imported by: 2
- Matching tests: 2

## Classes

- `EvolutionLog`
- `EvolutionRecord`
- `FixProposal`
- `FixProposer`
- `Gap`
- `PatchApplicator`
- `PatchPreview`
- `SelfEvolutionEngine`
- `SourceScanner`
- `Validator`
- `_GitSandbox`

## Functions

- `__init__`
- `_approval_metadata`
- `_build_prompt`
- `_changed_line_count`
- `_cleanup_git_sandbox`
- `_commit`
- `_create_git_sandbox`
- `_detect_python_executable`
- `_find_block_end`
- `_find_block_start`
- `_first_meaningful_line`
- `_git`
- `_git_is_dirty`
- `_header_signature`
- `_is_safe_file`
- `_load`
- `_normalize`
- `_normalize_branch_prefix`
- `_normalized_patch_lines`
- `_now_monotonic`
- `_parse_response`
- `_scan_file_lines`
- `_utc_iso`
- `append`
- `apply`
- `get`
- `preview`
- `read_context`
- `recent`
- `review_run`
- `run_pytest`
- `run_ruff`
- `scan`
- `scan_reference_gaps`
- `scan_roadmap`
- `status`
- `update`
- `_call` (async)
- `_do_run` (async)
- `_notify_operator` (async)
- `_restore_backups` (async)
- `propose` (async)
- `run_once` (async)

## Constants

- `MAX_FILES_PER_RUN`
- `MAX_LINES_DELTA`
- `THING_THRESHOLD`
- `THING_VOTES`
- `_BRANCH_SEGMENT_RE`
- `_DEF_LINE`
- `_DENYLIST_NAMES`
- `_GAP_PATTERN`
- `_RAISE_NOT_IMPL`
- `_ROADMAP_UNCHECKED`
- `_SELF_FILE`
- `_STUB_BODY`

## Notable String Markers

- `clawlite self-evolution`
- `test_ok`
- `test_out`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/self_evolution.py`.
- Cross-reference `CONNECTIONS_self_evolution.md` to see how this file fits into the wider system.
