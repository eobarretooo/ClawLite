# READ tests/providers/test_litellm_retry.py

## Identity

- Path: `tests/providers/test_litellm_retry.py`
- Area: `tests`
- Extension: `.py`
- Lines: 401
- Size bytes: 15425
- SHA1: `0cca0f75baef496b5550cf0985adb6fcebfa28b0`

## Summary

`tests.providers.test_litellm_retry` is a Python module in the `tests` area. It defines 2 class(es), led by `_Client`, `_FakeResponse`. It exposes 21 function(s), including `__init__`, `json`, `raise_for_status`, `__aenter__`, `__aexit__`, `_scenario`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 17
- Async functions: 4
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_Client`
- `_FakeResponse`

## Functions

- `__init__`
- `json`
- `raise_for_status`
- `test_litellm_provider_allows_local_runtime_without_api_key`
- `test_litellm_provider_circuit_opens_then_closes_after_cooldown`
- `test_litellm_provider_diagnostics_contract_and_secret_safety`
- `test_litellm_provider_invalid_empty_choices_returns_controlled_error`
- `test_litellm_provider_invalid_malformed_payload_returns_controlled_error`
- `test_litellm_provider_parses_tool_calls`
- `test_litellm_provider_passes_reasoning_effort_for_openai`
- `test_litellm_provider_preserves_auth_error_when_oauth_refresh_fails`
- `test_litellm_provider_quota_429_fails_fast_without_retry`
- `test_litellm_provider_refreshes_oauth_once_on_401_then_retries`
- `test_litellm_provider_retries_transient_5xx_then_success`
- `test_litellm_provider_retry_after_header_overrides_backoff`
- `test_litellm_provider_reuses_single_async_client_across_retries`
- `test_litellm_provider_uses_shared_quota_signal_source`
- `__aenter__` (async)
- `__aexit__` (async)
- `_scenario` (async)
- `post` (async)

## Notable String Markers

- `test_api_key_value`
- `test_litellm_provider_allows_local_runtime_without_api_key`
- `test_litellm_provider_circuit_opens_then_closes_after_cooldown`
- `test_litellm_provider_diagnostics_contract_and_secret_safety`
- `test_litellm_provider_invalid_empty_choices_returns_controlled_error`
- `test_litellm_provider_invalid_malformed_payload_returns_controlled_error`
- `test_litellm_provider_parses_tool_calls`
- `test_litellm_provider_passes_reasoning_effort_for_openai`
- `test_litellm_provider_preserves_auth_error_when_oauth_refresh_fails`
- `test_litellm_provider_quota_429_fails_fast_without_retry`
- `test_litellm_provider_refreshes_oauth_once_on_401_then_retries`
- `test_litellm_provider_retries_transient_5xx_then_success`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/providers/test_litellm_retry.py`.
- Cross-reference `CONNECTIONS_test_litellm_retry.md` to see how this file fits into the wider system.
