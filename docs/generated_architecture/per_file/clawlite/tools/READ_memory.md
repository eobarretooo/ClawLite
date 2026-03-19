# READ clawlite/tools/memory.py

## Identity

- Path: `clawlite/tools/memory.py`
- Area: `tools`
- Extension: `.py`
- Lines: 804
- Size bytes: 32439
- SHA1: `b3f160c8bfed6ee93a8ca126f6f743d2bfdae4ef`

## Summary

`clawlite.tools.memory` is a Python module in the `tools` area. It defines 6 class(es), led by `MemoryAnalyzeTool`, `MemoryForgetTool`, `MemoryGetTool`, `MemoryLearnTool`. It exposes 20 function(s), including `__init__`, `_accepts_parameter`, `_assert_allowed_scope`, `run`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 6
- Functions: 19
- Async functions: 1
- Constants: 2
- Internal imports: 2
- Imported by: 3
- Matching tests: 30

## Classes

- `MemoryAnalyzeTool`
- `MemoryForgetTool`
- `MemoryGetTool`
- `MemoryLearnTool`
- `MemoryRecallTool`
- `MemorySearchTool`

## Functions

- `__init__`
- `_accepts_parameter`
- `_assert_allowed_scope`
- `_callable_identity`
- `_clamp_int`
- `_clamp_lines`
- `_coerce_bool`
- `_coerce_float`
- `_coerce_reasoning_layers`
- `_discover_non_query_candidates`
- `_dump_json`
- `_memory_ref`
- `_normalize_ref_prefix`
- `_parse_from`
- `_public_memory_item`
- `_record_from_backend_payload`
- `_resolve_candidate_path`
- `_truncate_text`
- `args_schema`
- `run` (async)

## Constants

- `_SIGNATURE_PARAM_CACHE`
- `_SIGNATURE_PARAM_CACHE_MAX_SIZE`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/memory.py`.
- Cross-reference `CONNECTIONS_memory.md` to see how this file fits into the wider system.
