# READ clawlite/runtime/autonomy_actions.py

## Identity

- Path: `clawlite/runtime/autonomy_actions.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 1048
- Size bytes: 44830
- SHA1: `3ada24955904ea75d74a8e9d826ee26a288bac17`

## Summary

`clawlite.runtime.autonomy_actions` is a Python module in the `runtime` area. It defines 1 class(es), led by `AutonomyActionController`. It exposes 33 function(s), including `__init__`, `_action_confidence`, `_append_recent_audits`, `process`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 32
- Async functions: 1
- Constants: 3
- Internal imports: 0
- Imported by: 2
- Matching tests: 2

## Classes

- `AutonomyActionController`

## Functions

- `__init__`
- `_action_confidence`
- `_append_recent_audits`
- `_build_decision_view`
- `_clamp_confidence`
- `_clamp_dead_letter_args`
- `_classify_risk`
- `_clean_args`
- `_context_penalty`
- `_current_guardrails`
- `_default_confidence_for_action`
- `_denylisted`
- `_detect_degraded`
- `_evaluate_gates`
- `_excerpt`
- `_extract_first_json_object`
- `_new_action_status`
- `_normalize_environment_profile`
- `_normalize_policy`
- `_overall_risk_level`
- `_parse_actions`
- `_per_action_row`
- `_persist_audits`
- `_prune_rate_window`
- `_rate_window`
- `_trace_row`
- `_utc_now_iso`
- `explain`
- `export_audit`
- `set_environment_profile`
- `simulate`
- `status`
- `process` (async)

## Constants

- `ALLOWLIST`
- `DENYLIST_TOKENS`
- `ENVIRONMENT_PRESETS`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/autonomy_actions.py`.
- Cross-reference `CONNECTIONS_autonomy_actions.md` to see how this file fits into the wider system.
