# READ tests/core/test_skills.py

## Identity

- Path: `tests/core/test_skills.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1008
- Size bytes: 34467
- SHA1: `f25f1d4a35a8a2c5b1c257f3741b861bffbbea9f`

## Summary

`tests.core.test_skills` is a Python module in the `tests` area. It defines 1 class(es), led by `_FakeWatchfiles`. It exposes 39 function(s), including `__init__`, `_fake_which`, `_flaky_refresh`, `_scenario`, `awatch`, `emit`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 36
- Async functions: 3
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeWatchfiles`

## Functions

- `__init__`
- `_fake_which`
- `_flaky_refresh`
- `_now`
- `test_build_skills_summary_returns_xml`
- `test_clear_version_pin`
- `test_fallback_hint_not_shown_for_available_skill`
- `test_fallback_hint_parsed_from_frontmatter`
- `test_load_skill_full_returns_complete_content`
- `test_skills_loader_always_on_filters_unavailable`
- `test_skills_loader_applies_bundled_allowlist_without_blocking_workspace_override`
- `test_skills_loader_applies_profiled_skill_entries`
- `test_skills_loader_can_load_body_and_render_prompt`
- `test_skills_loader_debounces_skill_file_refreshes`
- `test_skills_loader_diagnostics_report_aggregates_deterministically`
- `test_skills_loader_diagnostics_report_marks_doc_only_as_not_runnable`
- `test_skills_loader_discovers_skill_md`
- `test_skills_loader_duplicate_policy_prefers_workspace_over_builtin`
- `test_skills_loader_marks_explicit_empty_name_as_invalid`
- `test_skills_loader_marks_invalid_execution_contract`
- `test_skills_loader_marks_unavailable_when_requirements_missing`
- `test_skills_loader_normalizes_requirement_schema_and_reports_invalid_env_names`
- `test_skills_loader_parses_multiline_metadata_json`
- `test_skills_loader_parses_nested_yaml_metadata`
- `test_skills_loader_parses_nested_yaml_requirements`
- `test_skills_loader_persists_enable_disable_and_pin_state`
- `test_skills_loader_respects_config_entry_disable`
- `test_skills_loader_supports_openclaw_any_bins_requirement`
- `test_skills_loader_supports_openclaw_primary_env_and_config_requirements`
- `test_skills_loader_uses_skill_entries_api_key_for_primary_env`
- `test_skills_loader_watcher_refreshes_pending_skill_changes`
- `test_skills_loader_watcher_survives_refresh_failure`
- `test_skills_loader_watcher_uses_watchfiles_backend_when_available`
- `test_version_pin_persisted_and_reflected`
- `test_version_pin_returns_none_for_unknown_skill`
- `test_version_pin_shown_in_diagnostics_report`
- `_scenario` (async)
- `awatch` (async)
- `emit` (async)

## Notable String Markers

- `test_build_skills_summary_returns_xml`
- `test_clear_version_pin`
- `test_fallback_hint_not_shown_for_available_skill`
- `test_fallback_hint_parsed_from_frontmatter`
- `test_load_skill_full_returns_complete_content`
- `test_skills_loader_always_on_filters_unavailable`
- `test_skills_loader_applies_bundled_allowlist_without_blocking_workspace_override`
- `test_skills_loader_applies_profiled_skill_entries`
- `test_skills_loader_can_load_body_and_render_prompt`
- `test_skills_loader_debounces_skill_file_refreshes`
- `test_skills_loader_diagnostics_report_aggregates_deterministically`
- `test_skills_loader_diagnostics_report_marks_doc_only_as_not_runnable`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_skills.py`.
- Cross-reference `CONNECTIONS_test_skills.md` to see how this file fits into the wider system.
