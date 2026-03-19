# READ tests/providers/test_failover.py

## Identity

- Path: `tests/providers/test_failover.py`
- Area: `tests`
- Extension: `.py`
- Lines: 357
- Size bytes: 13897
- SHA1: `bb300e6a2d5e60e580c02f27446de5832f0fb4e1`

## Summary

`tests.providers.test_failover` is a Python module in the `tests` area. It defines 3 class(es), led by `_Clock`, `_Provider`, `_SequenceProvider`. It exposes 18 function(s), including `__init__`, `advance`, `diagnostics`, `_scenario`, `complete`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 16
- Async functions: 2
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_Clock`
- `_Provider`
- `_SequenceProvider`

## Functions

- `__init__`
- `advance`
- `diagnostics`
- `get_default_model`
- `now`
- `test_failover_provider_auth_error_applies_hard_suppression_window`
- `test_failover_provider_cooldown_expires_and_primary_is_retried`
- `test_failover_provider_diagnostics_contract_and_secret_safety`
- `test_failover_provider_does_not_use_fallback_for_non_retryable_error`
- `test_failover_provider_fallback_cooldown_avoids_repeated_attempts`
- `test_failover_provider_operator_clear_suppression_resets_candidate_state`
- `test_failover_provider_primary_cooldown_skips_primary_and_uses_fallback`
- `test_failover_provider_quota_error_applies_extended_suppression_window`
- `test_failover_provider_tracks_fallback_failures`
- `test_failover_provider_uses_fallback_for_retryable_primary_failure`
- `test_failover_provider_uses_next_available_candidate_in_chain`
- `_scenario` (async)
- `complete` (async)

## Notable String Markers

- `test_failover_provider_auth_error_applies_hard_suppression_window`
- `test_failover_provider_cooldown_expires_and_primary_is_retried`
- `test_failover_provider_diagnostics_contract_and_secret_safety`
- `test_failover_provider_does_not_use_fallback_for_non_retryable_error`
- `test_failover_provider_fallback_cooldown_avoids_repeated_attempts`
- `test_failover_provider_operator_clear_suppression_resets_candidate_state`
- `test_failover_provider_primary_cooldown_skips_primary_and_uses_fallback`
- `test_failover_provider_quota_error_applies_extended_suppression_window`
- `test_failover_provider_tracks_fallback_failures`
- `test_failover_provider_uses_fallback_for_retryable_primary_failure`
- `test_failover_provider_uses_next_available_candidate_in_chain`
- `test_token_value`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/providers/test_failover.py`.
- Cross-reference `CONNECTIONS_test_failover.md` to see how this file fits into the wider system.
