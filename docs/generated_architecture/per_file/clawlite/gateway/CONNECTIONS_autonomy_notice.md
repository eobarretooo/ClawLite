# CONNECTIONS clawlite/gateway/autonomy_notice.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/core/memory_monitor.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/gateway/server.py`

## Matching Tests

- `tests/runtime/test_autonomy.py`

## Mermaid

```mermaid
flowchart TD
    N0["autonomy_notice.py"]
    D1["clawlite/core/memory_monitor.py"]
    D2["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/gateway/server.py"]
    T1["tests/runtime/test_autonomy.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
