# CONNECTIONS clawlite/runtime/supervisor.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 4.

## Internal Imports

- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/runtime/__init__.py`
- `tests/runtime/test_supervisor.py`
- `tests/runtime/test_supervisor_phase5.py`

## Matching Tests

- `tests/gateway/test_supervisor_recovery.py`
- `tests/gateway/test_supervisor_runtime.py`
- `tests/runtime/test_supervisor.py`
- `tests/runtime/test_supervisor_phase5.py`

## Mermaid

```mermaid
flowchart TD
    N0["supervisor.py"]
    D1["clawlite/utils/logging.py"]
    R1["clawlite/runtime/__init__.py"]
    R2["tests/runtime/test_supervisor.py"]
    R3["tests/runtime/test_supervisor_phase5.py"]
    T1["tests/gateway/test_supervisor_recovery.py"]
    T2["tests/gateway/test_supervisor_runtime.py"]
    T3["tests/runtime/test_supervisor.py"]
    T4["tests/runtime/test_supervisor_phase5.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
    T4 -->|tests| N0
```
