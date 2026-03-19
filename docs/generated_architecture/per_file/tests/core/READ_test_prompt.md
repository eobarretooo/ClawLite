# READ tests/core/test_prompt.py

## Identity

- Path: `tests/core/test_prompt.py`
- Area: `tests`
- Extension: `.py`
- Lines: 319
- Size bytes: 11191
- SHA1: `c9d8b18eb6ae0ebb8cfcdfd6b01f5379594dfc6c`

## Summary

`tests.core.test_prompt` is a Python module in the `tests` area. It exposes 15 function(s), including `test_prompt_builder_adds_always_on_identity_guard_section`, `test_prompt_builder_applies_token_budget_shaping_deterministically`, `test_prompt_builder_injects_identity_first_when_identity_empty`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 15
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `test_prompt_builder_adds_always_on_identity_guard_section`
- `test_prompt_builder_applies_token_budget_shaping_deterministically`
- `test_prompt_builder_injects_identity_first_when_identity_empty`
- `test_prompt_builder_injects_identity_first_when_identity_missing`
- `test_prompt_builder_injects_structured_user_profile_hint`
- `test_prompt_builder_keeps_stable_section_order_and_sorted_skills`
- `test_prompt_builder_omits_history_summary_when_history_fits_budget`
- `test_prompt_builder_omits_raw_default_user_profile_from_system_prompt`
- `test_prompt_builder_preserves_soul_and_structured_user_profile_under_workspace_pressure`
- `test_prompt_builder_reads_workspace_files`
- `test_prompt_builder_replaces_legacy_identity_fallback_with_stable_identity`
- `test_prompt_builder_runtime_context_includes_timezone_offset`
- `test_prompt_builder_skips_oversized_noncritical_workspace_files`
- `test_prompt_builder_token_estimate_is_deterministic_and_not_len_div_4`
- `test_prompt_builder_truncates_oversized_critical_workspace_files`

## Notable String Markers

- `test_prompt_builder_adds_always_on_identity_guard_section`
- `test_prompt_builder_applies_token_budget_shaping_deterministically`
- `test_prompt_builder_injects_identity_first_when_identity_empty`
- `test_prompt_builder_injects_identity_first_when_identity_missing`
- `test_prompt_builder_injects_structured_user_profile_hint`
- `test_prompt_builder_keeps_stable_section_order_and_sorted_skills`
- `test_prompt_builder_omits_history_summary_when_history_fits_budget`
- `test_prompt_builder_omits_raw_default_user_profile_from_system_prompt`
- `test_prompt_builder_preserves_soul_and_structured_user_profile_under_workspace_pressure`
- `test_prompt_builder_reads_workspace_files`
- `test_prompt_builder_replaces_legacy_identity_fallback_with_stable_identity`
- `test_prompt_builder_runtime_context_includes_timezone_offset`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_prompt.py`.
- Cross-reference `CONNECTIONS_test_prompt.md` to see how this file fits into the wider system.
