# CONNECTIONS clawlite/tools/exec.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 5 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/core/runestone.py`
- `clawlite/tools/base.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/tools/process.py`
- `tests/tools/test_exec_files.py`
- `tests/tools/test_exec_network_guard.py`
- `tests/tools/test_health_check.py`

## Matching Tests

- `tests/tools/test_exec_files.py`
- `tests/tools/test_exec_network_guard.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["exec.py"]
    D1["clawlite/core/runestone.py"]
    D2["clawlite/tools/base.py"]
    D3["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/tools/process.py"]
    R3["tests/tools/test_exec_files.py"]
    R4["tests/tools/test_exec_network_guard.py"]
    R5["tests/tools/test_health_check.py"]
    T1["tests/tools/test_exec_files.py"]
    T2["tests/tools/test_exec_network_guard.py"]
    T3["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
