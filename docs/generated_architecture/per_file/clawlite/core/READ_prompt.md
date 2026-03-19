# READ clawlite/core/prompt.py

## Identity

- Path: `clawlite/core/prompt.py`
- Area: `core`
- Extension: `.py`
- Lines: 506
- Size bytes: 20711
- SHA1: `344a058eca9da8eb599fa8b6a469978c07c569d4`

## Summary

`clawlite.core.prompt` is a Python module in the `core` area. It defines 2 class(es), led by `PromptArtifacts`, `PromptBuilder`. It exposes 17 function(s), including `__init__`, `_ensure_identity_first`, `_estimate_tokens`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 17
- Async functions: 0
- Constants: 15
- Internal imports: 2
- Imported by: 4
- Matching tests: 1

## Classes

- `PromptArtifacts`
- `PromptBuilder`

## Functions

- `__init__`
- `_ensure_identity_first`
- `_estimate_tokens`
- `_fit_prioritized_segments`
- `_identity_fallback_section`
- `_normalize_history`
- `_read_workspace_files`
- `_render_memory`
- `_render_runtime_context`
- `_shape_context`
- `_shape_history`
- `_shape_memory_items`
- `_shape_system_prompt`
- `_split_workspace_sections`
- `_summarize_trimmed_history`
- `_truncate_text`
- `build`

## Constants

- `_CRITICAL_WORKSPACE_FILES`
- `_EXECUTION_GUARD_SECTION`
- `_FILE_SECTION_RE`
- `_IDENTITY_FALLBACK_BODY`
- `_IDENTITY_GUARD_SECTION`
- `_IDENTITY_HEADER`
- `_IDENTITY_PLACEHOLDER_RE`
- `_RUNTIME_CONTEXT_CLOSE_TAG`
- `_RUNTIME_CONTEXT_OPEN_TAG`
- `_RUNTIME_CONTEXT_TAG`
- `_RUNTIME_METADATA_FIELDS`
- `_TOKEN_CJK_RE`
- `_TOKEN_SYMBOL_RE`
- `_TOKEN_WORD_RE`
- `_TRUNCATED_SUFFIX`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/prompt.py`.
- Cross-reference `CONNECTIONS_prompt.md` to see how this file fits into the wider system.
