# READ clawlite/workspace/loader.py

## Identity

- Path: `clawlite/workspace/loader.py`
- Area: `workspace`
- Extension: `.py`
- Lines: 606
- Size bytes: 23821
- SHA1: `d85fcdf6680b745a7a845ce8bc2754e3881cfa39`

## Summary

`clawlite.workspace.loader` is a Python module in the `workspace` area. It defines 1 class(es), led by `WorkspaceLoader`. It exposes 38 function(s), including `__init__`, `_backup_runtime_file`, `_bootstrap_state_defaults`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 38
- Async functions: 0
- Constants: 4
- Internal imports: 1
- Imported by: 12
- Matching tests: 2

## Classes

- `WorkspaceLoader`

## Functions

- `__init__`
- `_backup_runtime_file`
- `_bootstrap_state_defaults`
- `_legacy_onboarding_completed`
- `_legacy_user_profile_needs_migration`
- `_onboarding_state_defaults`
- `_read_bootstrap_state`
- `_read_onboarding_state`
- `_reconcile_onboarding_state`
- `_render`
- `_render_template_file`
- `_runtime_file_issue`
- `_utcnow_iso`
- `_write_bootstrap_state`
- `_write_onboarding_state`
- `bootstrap`
- `bootstrap_path`
- `bootstrap_prompt`
- `bootstrap_state_path`
- `bootstrap_status`
- `complete`
- `complete_bootstrap`
- `ensure_runtime_files`
- `get_prompt`
- `heartbeat_prompt`
- `mark`
- `onboarding_state_path`
- `onboarding_status`
- `prompt_context`
- `read`
- `record_bootstrap_result`
- `runtime_health`
- `should_run`
- `should_run_bootstrap`
- `sync_templates`
- `system_context`
- `user_profile`
- `user_profile_prompt`

## Constants

- `DEFAULT_PROMPT_FILE_MAX_BYTES`
- `DEFAULT_VARS`
- `RUNTIME_CRITICAL_FILES`
- `TEMPLATE_FILES`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/workspace/loader.py`.
- Cross-reference `CONNECTIONS_loader.md` to see how this file fits into the wider system.
