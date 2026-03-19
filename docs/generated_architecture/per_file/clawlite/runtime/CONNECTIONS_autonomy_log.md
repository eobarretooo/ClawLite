# CONNECTIONS clawlite/runtime/autonomy_log.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/runtime/__init__.py`
- `tests/runtime/test_autonomy_log.py`

## Matching Tests

- `tests/runtime/test_autonomy.py`
- `tests/runtime/test_autonomy_log.py`

## Mermaid

```mermaid
flowchart TD
    N0["autonomy_log.py"]
    R1["clawlite/runtime/__init__.py"]
    R2["tests/runtime/test_autonomy_log.py"]
    T1["tests/runtime/test_autonomy.py"]
    T2["tests/runtime/test_autonomy_log.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
