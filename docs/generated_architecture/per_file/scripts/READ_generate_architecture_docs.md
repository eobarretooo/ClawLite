# READ scripts/generate_architecture_docs.py

## Identity

- Path: `scripts/generate_architecture_docs.py`
- Area: `scripts`
- Extension: `.py`
- Lines: 801
- Size bytes: 31737
- SHA1: `f2ea6d948f00fcf2dd929b1c5281685cf8a7e98f`

## Summary

`scripts.generate_architecture_docs` is a Python module in the `scripts` area. It defines 2 class(es), led by `FileInfo`, `PythonAnalyzer`. It exposes 30 function(s), including `__init__`, `_is_excluded`, `build_file_info`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 30
- Async functions: 0
- Constants: 7
- Internal imports: 0
- Imported by: 0
- Matching tests: 0

## Classes

- `FileInfo`
- `PythonAnalyzer`

## Functions

- `__init__`
- `_is_excluded`
- `build_file_info`
- `build_relationships`
- `classify_area`
- `discover_files`
- `extract_string_markers`
- `limited_list`
- `main`
- `make_slug`
- `mermaid_edges`
- `normalize_module`
- `read_text`
- `resolve_relative_import`
- `subsystem_summary`
- `summarize_python`
- `summarize_text_file`
- `visit_AnnAssign`
- `visit_Assign`
- `visit_AsyncFunctionDef`
- `visit_ClassDef`
- `visit_FunctionDef`
- `visit_Import`
- `visit_ImportFrom`
- `write_architecture_walkthrough`
- `write_flowcharts`
- `write_index`
- `write_per_file_docs`
- `write_project_structure`
- `write_text`

## Constants

- `CODE_EXTENSIONS`
- `EXCLUDED_DIR_NAMES`
- `EXCLUDED_PATH_PARTS`
- `OUTPUT_ROOT`
- `PER_FILE_ROOT`
- `ROOT`
- `TEXT_EXTENSIONS`

## Notable String Markers

- `test_cache`
- `test_info`
- `test_name`
- `test_path`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `scripts/generate_architecture_docs.py`.
- Cross-reference `CONNECTIONS_generate_architecture_docs.md` to see how this file fits into the wider system.
