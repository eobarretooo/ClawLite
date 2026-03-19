# READ clawlite/providers/litellm.py

## Identity

- Path: `clawlite/providers/litellm.py`
- Area: `providers`
- Extension: `.py`
- Lines: 812
- Size bytes: 38268
- SHA1: `fbe34a931c3b4f59f14040225f3bdaa50f990f88`

## Summary

`clawlite.providers.litellm` is a Python module in the `providers` area. It defines 1 class(es), led by `LiteLLMProvider`. It exposes 21 function(s), including `__init__`, `_anthropic_messages`, `_anthropic_tools`, `_complete_anthropic`, `_try_refresh_oauth`, `complete`. It depends on 13 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 16
- Async functions: 5
- Constants: 0
- Internal imports: 4
- Imported by: 6
- Matching tests: 2

## Classes

- `LiteLLMProvider`

## Functions

- `__init__`
- `_anthropic_messages`
- `_anthropic_tools`
- `_check_circuit`
- `_error_detail`
- `_error_payload`
- `_extract_text`
- `_invalid_response_error`
- `_is_hard_quota_429`
- `_parse_arguments`
- `_parse_tool_calls`
- `_record_failure`
- `_record_success`
- `_retry_delay`
- `diagnostics`
- `get_default_model`
- `_complete_anthropic` (async)
- `_try_refresh_oauth` (async)
- `complete` (async)
- `stream` (async)
- `warmup` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/providers/litellm.py`.
- Cross-reference `CONNECTIONS_litellm.md` to see how this file fits into the wider system.
