# READ tests/tools/test_exec_network_guard.py

## Identity

- Path: `tests/tools/test_exec_network_guard.py`
- Area: `tests`
- Extension: `.py`
- Lines: 106
- Size bytes: 3603
- SHA1: `0bda515a686035c09e731472040dbcd5d5e3503d`

## Summary

`tests.tools.test_exec_network_guard` is a Python module in the `tests` area. It exposes 16 function(s), including `_tool`, `test_curl_internal_url_blocked`, `test_curl_public_url_allowed`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 16
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `_tool`
- `test_curl_internal_url_blocked`
- `test_curl_public_url_allowed`
- `test_env_wrapped_python_blocked`
- `test_node_inline_fetch_blocked`
- `test_node_print_flag_blocked`
- `test_non_network_python_allowed`
- `test_python_inline_network_fetch_blocked`
- `test_python_inline_public_url_allowed`
- `test_validate_allows_public_url`
- `test_validate_blocks_127_0_0_1`
- `test_validate_blocks_localhost`
- `test_validate_blocks_metadata_ip`
- `test_validate_empty_url`
- `test_validate_non_http_scheme_ignored`
- `test_wget_internal_blocked`

## Notable String Markers

- `test_curl_internal_url_blocked`
- `test_curl_public_url_allowed`
- `test_env_wrapped_python_blocked`
- `test_node_inline_fetch_blocked`
- `test_node_print_flag_blocked`
- `test_non_network_python_allowed`
- `test_python_inline_network_fetch_blocked`
- `test_python_inline_public_url_allowed`
- `test_validate_allows_public_url`
- `test_validate_blocks_127_0_0_1`
- `test_validate_blocks_localhost`
- `test_validate_blocks_metadata_ip`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_exec_network_guard.py`.
- Cross-reference `CONNECTIONS_test_exec_network_guard.md` to see how this file fits into the wider system.
