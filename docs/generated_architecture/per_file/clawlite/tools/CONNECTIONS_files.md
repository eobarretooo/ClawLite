# CONNECTIONS clawlite/tools/files.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/tools/base.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/tools/test_exec_files.py`
- `tests/tools/test_files_edge_cases.py`

## Matching Tests

- `tests/tools/test_exec_files.py`
- `tests/tools/test_files_edge_cases.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["files.py"]
    D1["clawlite/tools/base.py"]
    D2["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/tools/test_exec_files.py"]
    R3["tests/tools/test_files_edge_cases.py"]
    T1["tests/tools/test_exec_files.py"]
    T2["tests/tools/test_files_edge_cases.py"]
    T3["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
