# READ clawlite/tools/apply_patch.py

## Identity

- Path: `clawlite/tools/apply_patch.py`
- Area: `tools`
- Extension: `.py`
- Lines: 309
- Size bytes: 11546
- SHA1: `e7013ac217b8f080953ed4accb4de06203f5f39a`

## Summary

`clawlite.tools.apply_patch` is a Python module in the `tools` area. It defines 5 class(es), led by `AddOp`, `ApplyPatchTool`, `DeleteOp`, `UpdateChunk`. It exposes 10 function(s), including `__init__`, `_apply_update_chunks`, `_parse_patch`, `run`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 5
- Functions: 9
- Async functions: 1
- Constants: 7
- Internal imports: 1
- Imported by: 2
- Matching tests: 2

## Classes

- `AddOp`
- `ApplyPatchTool`
- `DeleteOp`
- `UpdateChunk`
- `UpdateOp`

## Functions

- `__init__`
- `_apply_update_chunks`
- `_parse_patch`
- `_parse_update_chunk`
- `_relative`
- `_resolve_path`
- `_seek_chunk`
- `_write_text_atomic`
- `args_schema`
- `run` (async)

## Constants

- `ADD_FILE_MARKER`
- `BEGIN_PATCH_MARKER`
- `DELETE_FILE_MARKER`
- `END_OF_FILE_MARKER`
- `END_PATCH_MARKER`
- `MOVE_TO_MARKER`
- `UPDATE_FILE_MARKER`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/apply_patch.py`.
- Cross-reference `CONNECTIONS_apply_patch.md` to see how this file fits into the wider system.
