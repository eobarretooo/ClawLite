# CONNECTIONS clawlite/tools/apply_patch.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/tools/base.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/tools/test_apply_patch.py`

## Matching Tests

- `tests/tools/test_apply_patch.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["apply_patch.py"]
    D1["clawlite/tools/base.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/tools/test_apply_patch.py"]
    T1["tests/tools/test_apply_patch.py"]
    T2["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
