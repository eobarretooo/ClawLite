# READ clawlite/core/engine.py

## Identity

- Path: `clawlite/core/engine.py`
- Area: `core`
- Extension: `.py`
- Lines: 3776
- Size bytes: 163121
- SHA1: `14f09733fe0f89efd3e3c0523913c92495763bc6`

## Summary

`clawlite.core.engine` is a Python module in the `core` area. It defines 21 class(es), led by `AgentCancelledError`, `AgentEngine`, `AgentLoopError`, `InMemorySessionStore`. It exposes 120 function(s), including `__init__`, `_accepts_parameter`, `_append_session_message`, `_attach_subagent_memory_digests`, `_complete_provider`, `_emit_progress`. It depends on 23 import statement target(s).

## Structural Data

- Classes: 21
- Functions: 101
- Async functions: 19
- Constants: 39
- Internal imports: 12
- Imported by: 9
- Matching tests: 2

## Classes

- `AgentCancelledError`
- `AgentEngine`
- `AgentLoopError`
- `InMemorySessionStore`
- `LoopDetectionSettings`
- `ProgressEvent`
- `ProviderAuthError`
- `ProviderChunk`
- `ProviderConfigError`
- `ProviderHttpError`
- `ProviderNetworkError`
- `ProviderProtocol`
- `ProviderResult`
- `ProviderUnknownError`
- `SessionStoreProtocol`
- `ToolCall`
- `ToolRegistryProtocol`
- `TurnBudget`
- `_CallableParameterSpec`
- `_ProviderPlanRecord`
- `_ToolExecutionRecord`

## Functions

- `__init__`
- `_accepts_parameter`
- `_append_session_message`
- `_append_subagent_digest`
- `_append_web_sources`
- `_assistant_tool_calls`
- `_callable_cache_key`
- `_callable_parameter_spec`
- `_clamp_memory_search_limit`
- `_classify_provider_error`
- `_cleanup_expired_stop_requests`
- `_current_turn_has_live_lookup_evidence`
- `_current_turn_messages`
- `_detect_ping_pong_loop`
- `_detect_provider_plan_loop`
- `_detect_tool_loop`
- `_extract_web_source_urls`
- `_failure_fingerprint`
- `_filter_subagent_digest_rows`
- `_format_memory_snippet`
- `_format_session_recovery_snippet`
- `_get_bus_module`
- `_has_live_lookup_capability`
- `_is_identity_question`
- `_is_memory_retrieval_candidate`
- `_is_quota_429_detail`
- `_is_subagent_digest_record`
- `_live_lookup_failure_message`
- `_loop_recovery_notice`
- `_memory_integration_policy`
- `_memory_query_terms`
- `_memory_ref`
- `_memory_result_sufficient`
- `_memory_row_id`
- `_memory_search`
- `_merge_memory_rows`
- `_message_requests_web_research`
- `_normalize_error_text`
- `_normalize_identity_output`
- `_normalize_provider_result`
- `_normalize_reasoning_effort`
- `_plan_memory_snippets`
- `_postprocess_final_output`
- `_provider_error_message`
- `_provider_plan_signature`
- `_provider_result_field`
- `_prune_messages_for_turn`
- `_read_session_history_messages`
- `_record_retrieval_latency`
- `_record_retrieval_metrics`
- `_record_turn_latency`
- `_record_turn_metrics`
- `_resolve_reasoning_effort`
- `_resolve_runtime_context`
- `_resolve_turn_budget`
- `_rewrite_memory_query`
- `_routing_notice_for_turn`
- `_row_metadata`
- `_sanitize_retrieval_query`
- `_soften_unverified_web_claims`
- `_split_subagent_digest`
- `_stop_requested`
- `_stream_requires_full_run`
- `_strip_provider_self_attribution`
- `_subagent_digest_happened_at`
- `_subagent_digest_memory_text`
- `_subagent_digest_probe_limit`
- `_subagent_memory_query`
- `_subagent_parallel_group_metadata`
- `_subagent_parallel_group_text`
- `_subagent_target_session_ids`
- `_subagent_target_user_ids`
- `_tokenize_retrieval_text`
- `_tool_call_arguments`
- `_tool_call_arguments_for_transcript`
- `_tool_call_id`
- `_tool_call_ids`
- `_tool_call_label_for_error`
- `_tool_call_name`
- `_tool_call_raw_arguments`
- `_tool_call_raw_id`
- `_tool_call_raw_name`
- `_tool_call_signature_arguments`
- `_tool_call_skill_name_from_arguments`
- `_tool_outcome_hash`
- `_tool_result_indicates_success`
- `_tool_schema_names`
- `_tool_signature`
- `_truncate_tool_result`
- `_turn_requires_live_lookup`
- `_web_research_notice_for_turn`
- `add_url`
- `append`
- `clear_stop`
- `read`
- `read_messages`
- `repl`
- `request_stop`
- `retrieval_metrics_snapshot`
- `schema`
- `turn_metrics_snapshot`
- `_attach_subagent_memory_digests` (async)
- `_complete_provider` (async)
- `_emit_progress` (async)
- `_emotion_guidance` (async)
- `_gen` (async)
- `_get_session_lock` (async)
- `_inject_subagent_digest` (async)
- `_llm_compact_text` (async)
- `_maybe_compact_tool_result` (async)
- `_maybe_semantic_history_summary` (async)
- `_memory_integration_hint` (async)
- `_memory_integration_policy_async` (async)
- `_memory_profile_hint` (async)
- `_persist_subagent_digest_memory` (async)
- `_run_serialized` (async)
- `complete` (async)
- `execute` (async)
- `run` (async)
- `stream_run` (async)

## Constants

- `_BUS_MODULE`
- `_CLAWLITE_MENTION_RE`
- `_DIAGNOSTIC_SWITCH_THRESHOLD`
- `_DOCKER_REQUEST_RE`
- `_EXTERNAL_FRESH_LOOKUP_RE`
- `_GITHUB_REQUEST_RE`
- `_IDENTITY_QUESTION_RE`
- `_IDENTITY_STATEMENT`
- `_INTERNAL_FRESH_LOOKUP_RE`
- `_LIVE_LOOKUP_RETRY_NOTICE`
- `_LIVE_LOOKUP_SKILL_NAMES`
- `_MAX_DYNAMIC_MESSAGES_PER_TURN`
- `_MEMORY_HINT_TOKENS`
- `_MEMORY_QUERY_MAX_METRICS_CHARS`
- `_MEMORY_ROUTE_NEXT_QUERY`
- `_MEMORY_ROUTE_NO_RETRIEVE`
- `_MEMORY_ROUTE_RETRIEVE`
- `_MEMORY_STOPWORDS`
- `_MEMORY_TOKEN_RE`
- `_MEMORY_TRIVIAL_RE`
- `_MESSAGE_PRUNE_PADDING`
- `_PROVIDER_SELF_ATTRIBUTION_CLAUSE_RE`
- `_PROVIDER_SELF_ATTRIBUTION_RE`
- `_PROVIDER_SELF_ATTRIBUTION_SENTENCE_RE`
- `_QUOTA_429_SIGNALS`
- `_REASONING_ALIASES`
- `_ROUTING_HINT_HEADER`
- `_SUMMARIZE_REQUEST_RE`
- `_THINK_DIRECTIVE_RE`
- `_TOOL_CALL_ID_RE`
- `_TOOL_NAME_RE`
- `_TOOL_RESULT_TRUNCATED_SUFFIX`
- `_UP_TO_DATE_REQUEST_RE`
- `_URL_RE`
- `_WEATHER_REQUEST_RE`
- `_WEB_CLAIM_RE`
- `_WEB_RESEARCH_REQUEST_RE`
- `_WEB_RESEARCH_SYSTEM_NOTICE`
- `_WEB_TOOL_NAMES`

## Notable String Markers

- `test_outcome_hash`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/engine.py`.
- Cross-reference `CONNECTIONS_engine.md` to see how this file fits into the wider system.
