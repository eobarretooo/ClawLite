# READ tests/tools/test_mcp.py

## Identity

- Path: `tests/tools/test_mcp.py`
- Area: `tests`
- Extension: `.py`
- Lines: 209
- Size bytes: 7272
- SHA1: `f17e01afa1716f34bf9f77a8d0de6bac4318ac7c`

## Summary

`tests.tools.test_mcp` is a Python module in the `tests` area. It defines 1 class(es), led by `FakeClient`. It exposes 17 function(s), including `__init__`, `_invalid_json`, `_tool`, `__aenter__`, `__aexit__`, `_scenario`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 12
- Async functions: 5
- Constants: 0
- Internal imports: 3
- Imported by: 0
- Matching tests: 0

## Classes

- `FakeClient`

## Functions

- `__init__`
- `_invalid_json`
- `_tool`
- `test_mcp_tool_blocks_private_resolved_ip`
- `test_mcp_tool_http_status_error_is_deterministic`
- `test_mcp_tool_invalid_json_response_is_deterministic`
- `test_mcp_tool_legacy_url_must_match_registry`
- `test_mcp_tool_namespaced_server_lookup`
- `test_mcp_tool_retries_transient_timeout_then_succeeds`
- `test_mcp_tool_retries_with_single_client_instance`
- `test_mcp_tool_timeout_enforced`
- `test_mcp_tool_transport_policy_blocks_disallowed_host`
- `__aenter__` (async)
- `__aexit__` (async)
- `_scenario` (async)
- `_slow_post` (async)
- `post` (async)

## Notable String Markers

- `test_mcp_tool_blocks_private_resolved_ip`
- `test_mcp_tool_http_status_error_is_deterministic`
- `test_mcp_tool_invalid_json_response_is_deterministic`
- `test_mcp_tool_legacy_url_must_match_registry`
- `test_mcp_tool_namespaced_server_lookup`
- `test_mcp_tool_retries_transient_timeout_then_succeeds`
- `test_mcp_tool_retries_with_single_client_instance`
- `test_mcp_tool_timeout_enforced`
- `test_mcp_tool_transport_policy_blocks_disallowed_host`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_mcp.py`.
- Cross-reference `CONNECTIONS_test_mcp.md` to see how this file fits into the wider system.
