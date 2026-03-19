# READ tests/providers/test_codex_retry.py

## Identity

- Path: `tests/providers/test_codex_retry.py`
- Area: `tests`
- Extension: `.py`
- Lines: 524
- Size bytes: 18519
- SHA1: `8664f4a5b97080f8093d3bc166c88d199cd289b5`

## Summary

`tests.providers.test_codex_retry` is a Python module in the `tests` area. It defines 2 class(es), led by `_Client`, `_FakeResponse`. It exposes 21 function(s), including `__init__`, `json`, `raise_for_status`, `__aenter__`, `__aexit__`, `_scenario`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 17
- Async functions: 4
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_Client`
- `_FakeResponse`

## Functions

- `__init__`
- `json`
- `raise_for_status`
- `test_codex_provider_circuit_opens_then_cooldown_closes`
- `test_codex_provider_classifies_auth_failure`
- `test_codex_provider_diagnostics_contract_and_secret_safety`
- `test_codex_provider_openai_compatible_override_keeps_chat_completions`
- `test_codex_provider_parses_responses_function_calls`
- `test_codex_provider_parses_sse_responses_backend`
- `test_codex_provider_parses_sse_without_event_stream_content_type`
- `test_codex_provider_parses_tool_calls_from_response`
- `test_codex_provider_passes_reasoning_effort`
- `test_codex_provider_retries_429_with_retry_after`
- `test_codex_provider_retries_5xx_then_success`
- `test_codex_provider_reuses_single_async_client_across_retries`
- `test_codex_provider_serializes_tools_for_responses_backend`
- `test_codex_provider_uses_responses_backend_by_default`
- `__aenter__` (async)
- `__aexit__` (async)
- `_scenario` (async)
- `post` (async)

## Notable String Markers

- `test_access_token_value`
- `test_codex_provider_circuit_opens_then_cooldown_closes`
- `test_codex_provider_classifies_auth_failure`
- `test_codex_provider_diagnostics_contract_and_secret_safety`
- `test_codex_provider_openai_compatible_override_keeps_chat_completions`
- `test_codex_provider_parses_responses_function_calls`
- `test_codex_provider_parses_sse_responses_backend`
- `test_codex_provider_parses_sse_without_event_stream_content_type`
- `test_codex_provider_parses_tool_calls_from_response`
- `test_codex_provider_passes_reasoning_effort`
- `test_codex_provider_retries_429_with_retry_after`
- `test_codex_provider_retries_5xx_then_success`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/providers/test_codex_retry.py`.
- Cross-reference `CONNECTIONS_test_codex_retry.md` to see how this file fits into the wider system.
