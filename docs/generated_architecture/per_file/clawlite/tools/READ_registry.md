# READ clawlite/tools/registry.py

## Identity

- Path: `clawlite/tools/registry.py`
- Area: `tools`
- Extension: `.py`
- Lines: 1280
- Size bytes: 54008
- SHA1: `6bb25dd6854bcf264b1ce2b3f53e37a28de82152`

## Summary

`clawlite.tools.registry` is a Python module in the `tools` area. It defines 3 class(es), led by `ToolRegistry`, `ToolResultCache`, `_CacheEntry`. It exposes 49 function(s), including `__init__`, `_add`, `_add_direct`, `execute`. It depends on 12 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 48
- Async functions: 1
- Constants: 8
- Internal imports: 3
- Imported by: 9
- Matching tests: 3

## Classes

- `ToolRegistry`
- `ToolResultCache`
- `_CacheEntry`

## Functions

- `__init__`
- `_add`
- `_add_direct`
- `_apply_layer`
- `_approval_context`
- `_approval_exact_grant_key`
- `_approval_grant_key`
- `_approval_request_id`
- `_arguments_preview`
- `_child_schema_path`
- `_command_specifier`
- `_derive_agent_from_session`
- `_derive_channel_from_session`
- `_derive_tool_specifiers`
- `_exec_env_key_fragments`
- `_exec_needs_shell_wrapper`
- `_exec_uses_explicit_shell_wrapper`
- `_format_argument_validation_failure`
- `_format_validation_error`
- `_has_approval_grant`
- `_is_channel_blocked`
- `_is_risky_by_safety`
- `_key`
- `_matched_specifier_rules`
- `_matches_schema_type`
- `_matches_specifier_rule`
- `_normalize_specifier_fragment`
- `_normalize_validation_errors`
- `_parse_approval_grant_key`
- `_prune_approval_state`
- `_register_approval_request`
- `_resolve_effective_safety`
- `_resolve_timeout`
- `_tool_exception_retryable`
- `_url_host_fragment`
- `_validate_arguments`
- `_validate_schema_value`
- `approval_grants_snapshot`
- `approval_requests_snapshot`
- `consume_pending_approval_requests`
- `get`
- `register`
- `replace`
- `review_approval_request`
- `revoke_approval_grants`
- `safety_decision`
- `schema`
- `set`
- `execute` (async)

## Constants

- `MAX_ENTRIES`
- `TTL_S`
- `_APPROVAL_REQUEST_LIMIT`
- `_EXEC_POSIX_SHELL_BINARIES`
- `_EXEC_POSIX_SHELL_FLAGS`
- `_EXEC_SHELL_META_RE`
- `_EXEC_WINDOWS_SHELL_BINARIES`
- `_EXEC_WINDOWS_SHELL_FLAGS`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/registry.py`.
- Cross-reference `CONNECTIONS_registry.md` to see how this file fits into the wider system.
