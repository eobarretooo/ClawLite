# CONNECTIONS clawlite/runtime/telemetry.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 6 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/core/engine.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/tools/registry.py`
- `tests/core/test_engine.py`
- `tests/runtime/test_runtime_telemetry.py`
- `tests/tools/test_registry.py`

## Matching Tests

- `tests/providers/test_telemetry.py`
- `tests/runtime/test_runtime_telemetry.py`

## Mermaid

```mermaid
flowchart TD
    N0["telemetry.py"]
    R1["clawlite/core/engine.py"]
    R2["clawlite/gateway/runtime_builder.py"]
    R3["clawlite/tools/registry.py"]
    R4["tests/core/test_engine.py"]
    R5["tests/runtime/test_runtime_telemetry.py"]
    R6["tests/tools/test_registry.py"]
    T1["tests/providers/test_telemetry.py"]
    T2["tests/runtime/test_runtime_telemetry.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
