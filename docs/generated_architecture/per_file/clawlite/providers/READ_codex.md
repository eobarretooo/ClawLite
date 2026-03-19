# READ clawlite/providers/codex.py

## Identity

- Path: `clawlite/providers/codex.py`
- Area: `providers`
- Extension: `.py`
- Lines: 627
- Size bytes: 27112
- SHA1: `8f394ac862c5d349b20b668771e1da6c28845f25`

## Summary

`clawlite.providers.codex` is a Python module in the `providers` area. It defines 1 class(es), led by `CodexProvider`. It exposes 25 function(s), including `__init__`, `_api_model_name`, `_check_circuit`, `complete`. It depends on 11 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 24
- Async functions: 1
- Constants: 2
- Internal imports: 2
- Imported by: 5
- Matching tests: 1

## Classes

- `CodexProvider`

## Functions

- `__init__`
- `_api_model_name`
- `_check_circuit`
- `_decode_responses_payload`
- `_extract_responses_text`
- `_extract_text`
- `_flush_event`
- `_parse_arguments`
- `_parse_responses_sse_text`
- `_parse_responses_tool_calls`
- `_parse_tool_calls`
- `_record_failure`
- `_record_success`
- `_response_error_detail`
- `_responses_event_error_detail`
- `_responses_input`
- `_responses_instructions`
- `_responses_tools`
- `_responses_url`
- `_retry_delay`
- `_uses_responses_api`
- `_uses_responses_api_base`
- `diagnostics`
- `get_default_model`
- `complete` (async)

## Constants

- `CODEX_DEFAULT_BASE_URL`
- `CODEX_DEFAULT_INSTRUCTIONS`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/providers/codex.py`.
- Cross-reference `CONNECTIONS_codex.md` to see how this file fits into the wider system.
