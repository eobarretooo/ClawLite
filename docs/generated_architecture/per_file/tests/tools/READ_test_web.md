# READ tests/tools/test_web.py

## Identity

- Path: `tests/tools/test_web.py`
- Area: `tests`
- Extension: `.py`
- Lines: 315
- Size bytes: 11480
- SHA1: `60d70fd392af5330fc1bb03a5f2b65549e44c417`

## Summary

`tests.tools.test_web` is a Python module in the `tests` area. It defines 4 class(es), led by `_DDGS`, `_FakeClient`, `_FakeNetworkStream`, `_FakeResponse`. It exposes 23 function(s), including `__enter__`, `__exit__`, `__init__`, `__aenter__`, `__aexit__`, `_scenario`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 4
- Functions: 19
- Async functions: 4
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_DDGS`
- `_FakeClient`
- `_FakeNetworkStream`
- `_FakeResponse`

## Functions

- `__enter__`
- `__exit__`
- `__init__`
- `_public_dns`
- `get_extra_info`
- `is_redirect`
- `json`
- `raise_for_status`
- `test_html_extractors_strip_multiline_blocks`
- `test_web_fetch_blocks_dns_resolution_drift`
- `test_web_fetch_blocks_peer_ip_mismatch`
- `test_web_fetch_blocks_private_target`
- `test_web_fetch_mode_json_requires_json_mime`
- `test_web_fetch_redirect_limit`
- `test_web_fetch_tool`
- `test_web_search_tool_falls_back_to_brave_when_ddg_is_unavailable`
- `test_web_search_tool_falls_back_to_searxng_after_ddg_and_brave_errors`
- `test_web_search_tool_returns_structured_payload`
- `text`
- `__aenter__` (async)
- `__aexit__` (async)
- `_scenario` (async)
- `get` (async)

## Notable String Markers

- `test_html_extractors_strip_multiline_blocks`
- `test_web_fetch_blocks_dns_resolution_drift`
- `test_web_fetch_blocks_peer_ip_mismatch`
- `test_web_fetch_blocks_private_target`
- `test_web_fetch_mode_json_requires_json_mime`
- `test_web_fetch_redirect_limit`
- `test_web_fetch_tool`
- `test_web_search_tool_falls_back_to_brave_when_ddg_is_unavailable`
- `test_web_search_tool_falls_back_to_searxng_after_ddg_and_brave_errors`
- `test_web_search_tool_returns_structured_payload`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_web.py`.
- Cross-reference `CONNECTIONS_test_web.md` to see how this file fits into the wider system.
