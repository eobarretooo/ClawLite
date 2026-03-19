# READ tests/tools/test_memory_tools.py

## Identity

- Path: `tests/tools/test_memory_tools.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1027
- Size bytes: 37730
- SHA1: `2a00babd1d1e4c3ee249daf3b6f217bb7fd6a4c7`

## Summary

`tests.tools.test_memory_tools` is a Python module in the `tests` area. It defines 7 class(es), led by `_AnalyzeAwareMemory`, `_AsyncMemory`, `_Backend`, `_BoundedMemory`. It exposes 49 function(s), including `__init__`, `_callable`, `_counting_signature`, `_scenario`, `memorize`, `retrieve`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 7
- Functions: 46
- Async functions: 3
- Constants: 0
- Internal imports: 4
- Imported by: 0
- Matching tests: 0

## Classes

- `_AnalyzeAwareMemory`
- `_AsyncMemory`
- `_Backend`
- `_BoundedMemory`
- `_FastPathMemory`
- `_QueryAwareMemory`
- `_TargetedMemory`

## Functions

- `__init__`
- `_callable`
- `_counting_signature`
- `_fake_embedding`
- `_parse_iso_timestamp`
- `add`
- `all`
- `analysis_stats`
- `curated`
- `delete_by_prefixes`
- `fetch_layer_records`
- `list_recent_candidates`
- `search`
- `test_accepts_parameter_uses_signature_cache`
- `test_memory_analyze_base_stats_fields`
- `test_memory_analyze_includes_reasoning_layers_and_confidence_blocks`
- `test_memory_analyze_includes_semantic_coverage_metadata`
- `test_memory_analyze_query_passes_session_context_and_surfaces_episodic_digest`
- `test_memory_analyze_query_returns_matches_with_refs`
- `test_memory_forget_by_query_enforces_min_length`
- `test_memory_forget_by_ref_deletes_from_history`
- `test_memory_forget_dry_run_returns_candidates_without_deletion`
- `test_memory_forget_non_query_prefers_bounded_memory_store_candidates`
- `test_memory_forget_query_uses_session_aware_search_when_supported`
- `test_memory_forget_ref_only_non_dry_run_uses_targeted_delete_path`
- `test_memory_forget_requires_selector`
- `test_memory_forget_source_dry_run_uses_backend_targeted_candidates_without_full_load`
- `test_memory_get_clamps_lines_to_safe_range`
- `test_memory_get_not_found_is_deterministic`
- `test_memory_get_reads_workspace_memory_markdown_slice`
- `test_memory_get_rejects_paths_outside_allowed_scope`
- `test_memory_get_supports_workspace_memory_md`
- `test_memory_learn_does_not_bypass_privacy_skip_with_add_fallback`
- `test_memory_learn_empty_error`
- `test_memory_learn_passes_user_context_when_memorize_supports_kwargs`
- `test_memory_learn_persists_reasoning_layer_and_confidence`
- `test_memory_learn_prefers_async_memorize_and_preserves_response_shape`
- `test_memory_learn_success`
- `test_memory_recall_forwards_reasoning_filters_and_returns_metadata`
- `test_memory_recall_limit_clamp`
- `test_memory_recall_passes_user_context_when_retrieve_supports_kwargs`
- `test_memory_recall_prefers_async_retrieve_and_preserves_response_shape`
- `test_memory_recall_surfaces_episodic_digest_from_retrieve`
- `test_memory_recall_with_metadata_default`
- `test_memory_recall_without_metadata`
- `test_memory_search_alias_reuses_recall_behavior`
- `_scenario` (async)
- `memorize` (async)
- `retrieve` (async)

## Notable String Markers

- `test_accepts_parameter_uses_signature_cache`
- `test_memory_analyze_base_stats_fields`
- `test_memory_analyze_includes_reasoning_layers_and_confidence_blocks`
- `test_memory_analyze_includes_semantic_coverage_metadata`
- `test_memory_analyze_query_passes_session_context_and_surfaces_episodic_digest`
- `test_memory_analyze_query_returns_matches_with_refs`
- `test_memory_forget_by_query_enforces_min_length`
- `test_memory_forget_by_ref_deletes_from_history`
- `test_memory_forget_dry_run_returns_candidates_without_deletion`
- `test_memory_forget_non_query_prefers_bounded_memory_store_candidates`
- `test_memory_forget_query_uses_session_aware_search_when_supported`
- `test_memory_forget_ref_only_non_dry_run_uses_targeted_delete_path`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_memory_tools.py`.
- Cross-reference `CONNECTIONS_test_memory_tools.md` to see how this file fits into the wider system.
