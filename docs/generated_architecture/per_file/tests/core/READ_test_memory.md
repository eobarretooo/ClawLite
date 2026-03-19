# READ tests/core/test_memory.py

## Identity

- Path: `tests/core/test_memory.py`
- Area: `tests`
- Extension: `.py`
- Lines: 2900
- Size bytes: 117851
- SHA1: `88a82af160a482bb32aab010499408507147a407`

## Summary

`tests.core.test_memory` is a Python module in the `tests` area. It defines 5 class(es), led by `_DetailedBackend`, `_FailingBackend`, `_FakeBM25`, `_Headers`. It exposes 143 function(s), including `__enter__`, `__exit__`, `__init__`, `_broken_completion`, `_consolidate_categories`, `_fake_aembedding`. It depends on 11 import statement target(s).

## Structural Data

- Classes: 5
- Functions: 137
- Async functions: 6
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_DetailedBackend`
- `_FailingBackend`
- `_FakeBM25`
- `_Headers`
- `_Response`

## Functions

- `__enter__`
- `__exit__`
- `__init__`
- `_blocked_locked_file`
- `_empty_fetch_layer_records`
- `_fake_embedding`
- `_fake_fetch_layer_records`
- `_fake_tokens`
- `_fake_urlopen`
- `_rewrite_record_created_at`
- `_spy_fsync`
- `_writer`
- `diagnostics`
- `get_content_charset`
- `get_content_type`
- `get_scores`
- `initialize`
- `is_supported`
- `read`
- `test_compute_salience_score_recent_beats_old`
- `test_consolidate_categories_is_callable`
- `test_consolidate_categories_returns_dict`
- `test_consolidate_categories_skips_when_below_threshold`
- `test_consolidation_loop_is_idempotent`
- `test_consolidation_loop_lifecycle`
- `test_decay_loop_is_idempotent`
- `test_decay_loop_lifecycle`
- `test_generate_embedding_fallback_order_tries_openai_after_gemini_failure`
- `test_memory_add_flushes_and_fsyncs_append_paths`
- `test_memory_add_is_concurrency_safe`
- `test_memory_add_reinforcement_stays_local_to_each_user_scope`
- `test_memory_add_reinforces_existing_hash_in_same_scope`
- `test_memory_analysis_stats_include_reasoning_layer_distribution_and_confidence_summary`
- `test_memory_async_memorize_ingests_text_file_path_with_default_modality`
- `test_memory_async_memorize_ingests_url_audio_fallback_text_and_modality`
- `test_memory_async_memorize_ingests_url_html_extracts_text_without_network`
- `test_memory_async_memorize_non_text_modality_fallback_keeps_reference_and_modality`
- `test_memory_async_memorize_supports_text_and_messages`
- `test_memory_async_retrieve_llm_returns_next_step_query_from_json`
- `test_memory_async_retrieve_rag_and_llm_fallback`
- `test_memory_branch_create_list_checkout_basics`
- `test_memory_compact_combines_expiry_decay_and_consolidation_results`
- `test_memory_consolidate`
- `test_memory_consolidate_deduplicates_by_source_checkpoint`
- `test_memory_consolidate_diagnostics_track_writes_and_dedup_hits`
- `test_memory_consolidate_global_signature_count_tracks_cross_session`
- `test_memory_consolidate_infers_profile_type_for_preferences`
- `test_memory_consolidate_promotes_repeated_facts_across_sessions`
- `test_memory_consolidate_reads_legacy_checkpoints_format`
- `test_memory_consolidate_skips_trivial_exchange`
- `test_memory_consolidate_updates_curated_layer`
- `test_memory_curated_prunes_low_rank_facts_when_oversized`
- `test_memory_decrypt_supports_legacy_enc_v1_rows`
- `test_memory_default_decay_rate_varies_by_memory_type`
- `test_memory_delete_by_prefixes_is_limit_bounded_and_keeps_repair_behavior`
- `test_memory_delete_by_prefixes_prunes_embedding_rows_for_deleted_ids`
- `test_memory_delete_by_prefixes_prunes_layer_files_and_backend_index`
- `test_memory_delete_by_prefixes_removes_from_history_and_curated`
- `test_memory_detect_emotional_tone_scores_excited_phrase`
- `test_memory_detect_emotional_tone_scores_frustrated_phrase`
- `test_memory_diagnostics_capture_backend_probe_details`
- `test_memory_diagnostics_expose_backend_health_defaults`
- `test_memory_diagnostics_preserve_backend_init_failure_details`
- `test_memory_emotional_tracking_flag_controls_add_tone_detection`
- `test_memory_encrypted_category_roundtrip_preserves_plain_reads`
- `test_memory_ephemeral_ttl_cleanup_deletes_expired_rows`
- `test_memory_ephemeral_ttl_cleanup_prunes_user_and_shared_scopes`
- `test_memory_history_prunes_when_store_exceeds_limit`
- `test_memory_history_read_tolerates_corrupt_lines_and_repairs_file`
- `test_memory_home_derivation_uses_state_sibling_mapping_and_keeps_local_behavior`
- `test_memory_infers_event_type_happened_at_and_structured_metadata`
- `test_memory_integration_hint_is_empty_for_normal_and_present_for_risk_modes`
- `test_memory_integration_policies_snapshot_returns_expected_shape`
- `test_memory_integration_policy_defaults_to_normal_on_empty_quality_state`
- `test_memory_integration_policy_uses_quality_state_for_degraded_and_severe_modes`
- `test_memory_list_recent_candidates_falls_back_to_bounded_recent_history_scan`
- `test_memory_list_recent_candidates_uses_backend_bounded_scan_without_history_full_read`
- `test_memory_memorize_add_persists_resource_item_and_category_layers`
- `test_memory_memorize_consolidate_persists_joined_resource_and_category_summary`
- `test_memory_memorize_skips_when_privacy_pattern_matches`
- `test_memory_merge_creates_snapshot_and_updates_target_head`
- `test_memory_migrates_legacy_profile_to_emotional_profile_path`
- `test_memory_migrates_legacy_state_embeddings_when_new_path_missing`
- `test_memory_privacy_skip_writes_audit_entry`
- `test_memory_profile_auto_update_from_preferences_timezone_and_topics`
- `test_memory_profile_prompt_hint_is_empty_for_default_profile`
- `test_memory_profile_prompt_hint_summarizes_learned_preferences`
- `test_memory_profile_tracks_upcoming_events_from_event_memory`
- `test_memory_quality_state_history_is_bounded`
- `test_memory_quality_state_legacy_call_without_reasoning_metrics_keeps_score_and_defaults`
- `test_memory_quality_state_reasoning_layers_report_structure_and_recommendations`
- `test_memory_quality_state_snapshot_normalizes_tuning_defaults_and_legacy_shapes`
- `test_memory_quality_state_update_persists_report_with_drift_and_recommendations`
- `test_memory_quality_tuning_recent_actions_is_bounded`
- `test_memory_reasoning_layer_and_confidence_roundtrip_on_write_and_read`
- `test_memory_record_normalization_fills_defaults_for_legacy_rows`
- `test_memory_recover_session_context_prefers_working_set_before_history_and_curated`
- `test_memory_recover_session_context_uses_history_then_curated_fallback`
- `test_memory_retrieve_progressive_loads_resource_hits_for_partial_item_coverage`
- `test_memory_retrieve_progressive_surfaces_category_stage_metadata`
- `test_memory_retrieve_surfaces_visible_episode_digest_by_session_relationship`
- `test_memory_scaffolds_hierarchical_home_directories_and_new_default_paths`
- `test_memory_search_and_retrieve_accept_naive_record_timestamps_in_date_filters`
- `test_memory_search_and_retrieve_apply_happened_at_window_with_missing_and_invalid_rows_non_matching`
- `test_memory_search_and_retrieve_apply_inclusive_created_at_window`
- `test_memory_search_and_retrieve_apply_list_filters_case_insensitively`
- `test_memory_search_and_retrieve_combine_filters_with_reasoning_confidence_and_shared_scope`
- `test_memory_search_and_retrieve_reject_unknown_filter_keys`
- `test_memory_search_and_retrieve_support_curated_modality_filters`
- `test_memory_search_and_retrieve_support_reasoning_layer_and_min_confidence_filters`
- `test_memory_search_decay_penalty_demotes_stale_high_decay_record_on_tie`
- `test_memory_search_entity_match_breaks_temporal_ties`
- `test_memory_search_hides_parent_only_sibling_episodes_but_allows_family_scope`
- `test_memory_search_hybrid_semantic_and_bm25_ranks_by_combined_score`
- `test_memory_search_include_shared_uses_semantic_ranking`
- `test_memory_search_is_deterministic_for_repeated_queries`
- `test_memory_search_prefers_overlap_even_with_negative_bm25`
- `test_memory_search_prefers_promoted_curated_fact`
- `test_memory_search_prioritizes_same_session_working_episode`
- `test_memory_search_salience_prefers_reinforced_record_on_close_tie`
- `test_memory_search_temporal_intent_prefers_temporal_marker_on_tie`
- `test_memory_search_user_scope_uses_semantic_ranking`
- `test_memory_search_uses_recency_to_break_lexical_and_bm25_ties`
- `test_memory_semantic_add_writes_embedding_file_when_enabled`
- `test_memory_semantic_backfill_populates_missing_embeddings_without_duplicates`
- `test_memory_shared_opt_in_controls_include_shared_results`
- `test_memory_snapshot_rollback_and_diff`
- `test_memory_store_add_and_search`
- `test_memory_type_constants_exist`
- `test_memory_update_quality_tuning_state_persists_without_history_growth_and_supports_update_patch`
- `test_memory_user_scoped_memorize_and_retrieve_isolated_by_default`
- `test_memory_working_set_auto_promotes_episode_snapshots_in_batches`
- `test_memory_working_set_keeps_siblings_isolated_until_family_share_is_enabled`
- `test_memory_working_set_persists_and_shares_parent_subagent_family`
- `test_purge_decayed_records_removes_fully_decayed`
- `test_purge_decayed_records_returns_dict`
- `test_purge_decayed_records_skips_zero_decay_rate`
- `_broken_completion` (async)
- `_consolidate_categories` (async)
- `_fake_aembedding` (async)
- `_json_completion` (async)
- `_purge_decayed` (async)
- `_scenario` (async)

## Notable String Markers

- `test_compute_salience_score_recent_beats_old`
- `test_consolidate_categories_is_callable`
- `test_consolidate_categories_returns_dict`
- `test_consolidate_categories_skips_when_below_threshold`
- `test_consolidation_loop_is_idempotent`
- `test_consolidation_loop_lifecycle`
- `test_decay_loop_is_idempotent`
- `test_decay_loop_lifecycle`
- `test_generate_embedding_fallback_order_tries_openai_after_gemini_failure`
- `test_memory_add_flushes_and_fsyncs_append_paths`
- `test_memory_add_is_concurrency_safe`
- `test_memory_add_reinforcement_stays_local_to_each_user_scope`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_memory.py`.
- Cross-reference `CONNECTIONS_test_memory.md` to see how this file fits into the wider system.
