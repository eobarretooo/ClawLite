# READ tests/runtime/test_autonomy_actions.py

## Identity

- Path: `tests/runtime/test_autonomy_actions.py`
- Area: `tests`
- Extension: `.py`
- Lines: 418
- Size bytes: 15558
- SHA1: `c4f6edb821a009fce67a0cb1dd1305bef4d7a5b1`

## Summary

`tests.runtime.test_autonomy_actions` is a Python module in the `tests` area. It defines 1 class(es), led by `_Clock`. It exposes 22 function(s), including `__init__`, `_diagnostics_snapshot`, `_validate_provider`, `_replay`, `_scenario`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 20
- Async functions: 2
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_Clock`

## Functions

- `__init__`
- `_diagnostics_snapshot`
- `_validate_provider`
- `monotonic`
- `test_allowlisted_action_executes`
- `test_audit_export_reads_persisted_entries`
- `test_contextual_penalty_can_block_high_base_confidence`
- `test_contextual_penalty_mild_still_allows_action_and_tracks_penalty`
- `test_cooldown_blocks_repeat`
- `test_dead_letter_replay_clamps_limit_and_forces_dry_run`
- `test_degraded_snapshot_blocks_non_diagnostics_and_allows_diagnostics`
- `test_explain_reports_risk_levels_recommendations_and_counts`
- `test_invalid_json_increments_parse_errors`
- `test_low_confidence_quality_gate_blocks_action`
- `test_process_audit_rows_include_trace_and_gate`
- `test_rate_limit_blocks_after_threshold`
- `test_set_environment_profile_applies_preset_and_audits_policy_change`
- `test_simulate_is_side_effect_free_for_execution_counters`
- `test_simulate_returns_decision_trace_for_mixed_actions`
- `test_unknown_and_denylisted_actions_blocked`
- `_replay` (async)
- `_scenario` (async)

## Notable String Markers

- `test_allowlisted_action_executes`
- `test_audit_export_reads_persisted_entries`
- `test_contextual_penalty_can_block_high_base_confidence`
- `test_contextual_penalty_mild_still_allows_action_and_tracks_penalty`
- `test_cooldown_blocks_repeat`
- `test_dead_letter_replay_clamps_limit_and_forces_dry_run`
- `test_degraded_snapshot_blocks_non_diagnostics_and_allows_diagnostics`
- `test_explain_reports_risk_levels_recommendations_and_counts`
- `test_invalid_json_increments_parse_errors`
- `test_low_confidence_quality_gate_blocks_action`
- `test_process_audit_rows_include_trace_and_gate`
- `test_rate_limit_blocks_after_threshold`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_autonomy_actions.py`.
- Cross-reference `CONNECTIONS_test_autonomy_actions.md` to see how this file fits into the wider system.
