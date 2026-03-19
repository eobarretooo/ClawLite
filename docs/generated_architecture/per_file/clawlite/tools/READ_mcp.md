# READ clawlite/tools/mcp.py

## Identity

- Path: `clawlite/tools/mcp.py`
- Area: `tools`
- Extension: `.py`
- Lines: 291
- Size bytes: 12585
- SHA1: `9647aefbe478a97e59b2d6bb6e5f8d4b99eb21cf`

## Summary

`clawlite.tools.mcp` is a Python module in the `tools` area. It defines 1 class(es), led by `MCPTool`. It exposes 18 function(s), including `__init__`, `_host_matches`, `_ip_literal`, `_resolve_ips_async`, `_validate_transport`, `health_check`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 14
- Async functions: 4
- Constants: 2
- Internal imports: 3
- Imported by: 3
- Matching tests: 3

## Classes

- `MCPTool`

## Functions

- `__init__`
- `_host_matches`
- `_ip_literal`
- `_is_private_or_local`
- `_match_any`
- `_normalize_url`
- `_parse_namespaced_tool`
- `_resolve_ips`
- `_resolve_target`
- `_resolve_timeout`
- `_rule_matches`
- `_server_name_from_url`
- `_strip_server_prefix`
- `args_schema`
- `_resolve_ips_async` (async)
- `_validate_transport` (async)
- `health_check` (async)
- `run` (async)

## Constants

- `_TRANSIENT_RETRY_ATTEMPTS`
- `_TRANSIENT_RETRY_BACKOFF_S`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/mcp.py`.
- Cross-reference `CONNECTIONS_mcp.md` to see how this file fits into the wider system.
