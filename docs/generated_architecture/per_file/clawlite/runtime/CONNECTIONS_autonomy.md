# CONNECTIONS clawlite/runtime/autonomy.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 4.

## Internal Imports

- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/runtime/__init__.py`
- `tests/runtime/test_autonomy.py`
- `tests/runtime/test_autonomy_wake.py`

## Matching Tests

- `tests/runtime/test_autonomy.py`
- `tests/runtime/test_autonomy_actions.py`
- `tests/runtime/test_autonomy_log.py`
- `tests/runtime/test_autonomy_wake.py`

## Mermaid

```mermaid
flowchart TD
    N0["autonomy.py"]
    D1["clawlite/utils/logging.py"]
    R1["clawlite/runtime/__init__.py"]
    R2["tests/runtime/test_autonomy.py"]
    R3["tests/runtime/test_autonomy_wake.py"]
    T1["tests/runtime/test_autonomy.py"]
    T2["tests/runtime/test_autonomy_actions.py"]
    T3["tests/runtime/test_autonomy_log.py"]
    T4["tests/runtime/test_autonomy_wake.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
    T4 -->|tests| N0
```
