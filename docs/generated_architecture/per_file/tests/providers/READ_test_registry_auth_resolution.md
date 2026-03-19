# READ tests/providers/test_registry_auth_resolution.py

## Identity

- Path: `tests/providers/test_registry_auth_resolution.py`
- Area: `tests`
- Extension: `.py`
- Lines: 577
- Size bytes: 20638
- SHA1: `95b8bd3453342f622caaf62162c341a51cdb0180`

## Summary

`tests.providers.test_registry_auth_resolution` is a Python module in the `tests` area. It exposes 32 function(s), including `test_build_provider_custom_accepts_extra_headers`, `test_build_provider_detects_ollama_from_local_base_url_without_api_key`, `test_build_provider_does_not_wrap_with_failover_when_same_model`, `_scenario`, `post_mock`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 30
- Async functions: 2
- Constants: 0
- Internal imports: 5
- Imported by: 0
- Matching tests: 0

## Functions

- `test_build_provider_custom_accepts_extra_headers`
- `test_build_provider_detects_ollama_from_local_base_url_without_api_key`
- `test_build_provider_does_not_wrap_with_failover_when_same_model`
- `test_build_provider_gemini_oauth_prefers_current_file_token_when_config_source_is_file`
- `test_build_provider_gemini_oauth_reads_auth_file_when_env_missing`
- `test_build_provider_openai_codex_accepts_auth_provider_alias_and_token_only`
- `test_build_provider_openai_codex_is_deterministic_even_without_codex_auth`
- `test_build_provider_openai_codex_prefers_codex_provider_when_auth_present`
- `test_build_provider_openai_codex_prefers_current_auth_file_when_config_source_is_file`
- `test_build_provider_openai_codex_reads_auth_file_when_env_missing`
- `test_build_provider_prefers_provider_specific_block_over_legacy`
- `test_build_provider_prefers_single_configured_vendor_for_generic_model`
- `test_build_provider_qwen_oauth_reads_auth_file_when_env_missing`
- `test_build_provider_qwen_oauth_refreshes_file_backed_token_on_401`
- `test_build_provider_uses_dynamic_xai_block`
- `test_build_provider_uses_groq_env_key`
- `test_build_provider_uses_minimax_anthropic_transport`
- `test_build_provider_wraps_with_failover_when_fallback_model_is_configured`
- `test_build_provider_wraps_with_multi_hop_failover_when_fallback_models_are_configured`
- `test_provider_returns_missing_key_error_before_http`
- `test_resolve_gateway_from_openrouter_key`
- `test_resolve_gemini_uses_provider_defaults`
- `test_resolve_kilocode_detects_gateway_from_base_url`
- `test_resolve_kimi_coding_uses_anthropic_transport`
- `test_resolve_litellm_provider_raises_explicit_error_without_specs`
- `test_resolve_minimax_uses_anthropic_transport`
- `test_resolve_openai_ignores_incompatible_configured_key`
- `test_resolve_openai_ignores_incompatible_generic_key_prefix`
- `test_resolve_xai_uses_provider_defaults`
- `test_resolve_zai_accepts_env_aliases`
- `_scenario` (async)
- `post_mock` (async)

## Notable String Markers

- `test_build_provider_custom_accepts_extra_headers`
- `test_build_provider_detects_ollama_from_local_base_url_without_api_key`
- `test_build_provider_does_not_wrap_with_failover_when_same_model`
- `test_build_provider_gemini_oauth_prefers_current_file_token_when_config_source_is_file`
- `test_build_provider_gemini_oauth_reads_auth_file_when_env_missing`
- `test_build_provider_openai_codex_accepts_auth_provider_alias_and_token_only`
- `test_build_provider_openai_codex_is_deterministic_even_without_codex_auth`
- `test_build_provider_openai_codex_prefers_codex_provider_when_auth_present`
- `test_build_provider_openai_codex_prefers_current_auth_file_when_config_source_is_file`
- `test_build_provider_openai_codex_reads_auth_file_when_env_missing`
- `test_build_provider_prefers_provider_specific_block_over_legacy`
- `test_build_provider_prefers_single_configured_vendor_for_generic_model`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/providers/test_registry_auth_resolution.py`.
- Cross-reference `CONNECTIONS_test_registry_auth_resolution.md` to see how this file fits into the wider system.
