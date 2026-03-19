# READ clawlite/tools/files.py

## Identity

- Path: `clawlite/tools/files.py`
- Area: `tools`
- Extension: `.py`
- Lines: 341
- Size bytes: 12411
- SHA1: `491d6a7dd431f585c3e8996cef6833a57b93891d`

## Summary

`clawlite.tools.files` is a Python module in the `tools` area. It defines 9 class(es), led by `EditFileTool`, `EditTool`, `FileToolError`, `FileToolPermissionError`. It exposes 8 function(s), including `__init__`, `__str__`, `_atomic_write_text`, `run`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 9
- Functions: 7
- Async functions: 1
- Constants: 4
- Internal imports: 2
- Imported by: 3
- Matching tests: 3

## Classes

- `EditFileTool`
- `EditTool`
- `FileToolError`
- `FileToolPermissionError`
- `ListDirTool`
- `ReadFileTool`
- `ReadTool`
- `WriteFileTool`
- `WriteTool`

## Functions

- `__init__`
- `__str__`
- `_atomic_write_text`
- `_build_not_found_message`
- `_safe_path`
- `_workspace_path`
- `args_schema`
- `run` (async)

## Constants

- `DEFAULT_MAX_EDIT_BYTES`
- `DEFAULT_MAX_READ_BYTES`
- `DEFAULT_MAX_WRITE_BYTES`
- `MAX_READ_CHUNK_BYTES`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/files.py`.
- Cross-reference `CONNECTIONS_files.md` to see how this file fits into the wider system.
