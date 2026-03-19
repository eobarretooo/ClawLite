# READ clawlite/tools/web.py

## Identity

- Path: `clawlite/tools/web.py`
- Area: `tools`
- Extension: `.py`
- Lines: 552
- Size bytes: 21796
- SHA1: `837b00a488e69c1b16f08a7c66cbe9c9df205f0f`

## Summary

`clawlite.tools.web` is a Python module in the `tools` area. It defines 2 class(es), led by `WebFetchTool`, `WebSearchTool`. It exposes 26 function(s), including `__init__`, `_build_client`, `_coerce_extra_info_to_ip`, `_request_with_redirects`, `_resolve_ips_async`, `_search_brave`. It depends on 13 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 19
- Async functions: 7
- Constants: 0
- Internal imports: 2
- Imported by: 3
- Matching tests: 2

## Classes

- `WebFetchTool`
- `WebSearchTool`

## Functions

- `__init__`
- `_build_client`
- `_coerce_extra_info_to_ip`
- `_error_payload`
- `_extract_content`
- `_extract_ip_from_extra_info`
- `_extract_peer_ip`
- `_has_ip_overlap`
- `_html_to_markdown`
- `_html_to_text`
- `_ip_literal`
- `_matches_rules`
- `_mime_type`
- `_normalize_brave_results`
- `_normalize_searxng_results`
- `_ok_payload`
- `_resolve_ips`
- `_search_ddgs_sync`
- `args_schema`
- `_request_with_redirects` (async)
- `_resolve_ips_async` (async)
- `_search_brave` (async)
- `_search_ddg` (async)
- `_search_searxng` (async)
- `_validate_target` (async)
- `run` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/web.py`.
- Cross-reference `CONNECTIONS_web.md` to see how this file fits into the wider system.
