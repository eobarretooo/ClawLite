# CONNECTIONS clawlite/tools/pdf.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/tools/base.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/tools/test_health_check.py`
- `tests/tools/test_tools.py`

## Matching Tests

- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["pdf.py"]
    D1["clawlite/tools/base.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/tools/test_health_check.py"]
    R3["tests/tools/test_tools.py"]
    T1["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
