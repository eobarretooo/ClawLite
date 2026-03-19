# READ tests/runtime/test_self_evolution.py

## Identity

- Path: `tests/runtime/test_self_evolution.py`
- Area: `tests`
- Extension: `.py`
- Lines: 656
- Size bytes: 26239
- SHA1: `246750c309b0896d7653c3ae6bd10512c79c352a`

## Summary

`tests.runtime.test_self_evolution` is a Python module in the `tests` area. It exposes 24 function(s), including `_build_sample_self_evolution_project`, `_build_validator_wrapper`, `_fake_run`, `_fake_llm`, `_fake_notify`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 22
- Async functions: 2
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `_build_sample_self_evolution_project`
- `_build_validator_wrapper`
- `_fake_run`
- `_git_output`
- `_unexpected_commit`
- `_validator_should_not_run`
- `test_patch_applicator_preserves_decorated_neighbor_block`
- `test_patch_applicator_rejects_header_mismatch`
- `test_patch_applicator_rejects_invalid_target_path`
- `test_self_evolution_dry_run_reports_preview_without_commit`
- `test_self_evolution_end_to_end_smoke_uses_isolated_branch`
- `test_self_evolution_fails_closed_when_primary_checkout_is_dirty`
- `test_self_evolution_first_run_ignores_cooldown_when_monotonic_is_low`
- `test_self_evolution_no_gaps_respects_cooldown_and_force`
- `test_self_evolution_rejects_unsafe_proposal_before_apply`
- `test_self_evolution_review_run_records_approval_state`
- `test_self_evolution_rolls_back_when_commit_fails`
- `test_self_evolution_rolls_back_when_pytest_fails`
- `test_self_evolution_run_once_commits_and_notifies`
- `test_self_evolution_supports_branch_prefix_and_approval_notice`
- `test_validator_fails_closed_when_python_executable_is_missing`
- `test_validator_prefers_project_venv_python_for_ruff_and_pytest`
- `_fake_llm` (async)
- `_fake_notify` (async)

## Notable String Markers

- `test_ok`
- `test_output`
- `test_patch_applicator_preserves_decorated_neighbor_block`
- `test_patch_applicator_rejects_header_mismatch`
- `test_patch_applicator_rejects_invalid_target_path`
- `test_sample`
- `test_self_evolution_dry_run_reports_preview_without_commit`
- `test_self_evolution_end_to_end_smoke_uses_isolated_branch`
- `test_self_evolution_fails_closed_when_primary_checkout_is_dirty`
- `test_self_evolution_first_run_ignores_cooldown_when_monotonic_is_low`
- `test_self_evolution_no_gaps_respects_cooldown_and_force`
- `test_self_evolution_rejects_unsafe_proposal_before_apply`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_self_evolution.py`.
- Cross-reference `CONNECTIONS_test_self_evolution.md` to see how this file fits into the wider system.
