# CONNECTIONS clawlite/gateway/engine_diagnostics.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_engine_diagnostics.py`

## Matching Tests

- `tests/core/test_engine.py`
- `tests/gateway/test_engine_diagnostics.py`

## Mermaid

```mermaid
flowchart TD
    N0["engine_diagnostics.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_engine_diagnostics.py"]
    T1["tests/core/test_engine.py"]
    T2["tests/gateway/test_engine_diagnostics.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
