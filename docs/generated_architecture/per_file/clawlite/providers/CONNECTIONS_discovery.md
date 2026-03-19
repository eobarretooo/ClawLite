# CONNECTIONS clawlite/providers/discovery.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 5 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/providers/registry.py`
- `tests/providers/test_discovery.py`

## Matching Tests

- `tests/providers/test_discovery.py`

## Mermaid

```mermaid
flowchart TD
    N0["discovery.py"]
    R1["clawlite/cli/onboarding.py"]
    R2["clawlite/cli/ops.py"]
    R3["clawlite/gateway/runtime_builder.py"]
    R4["clawlite/providers/registry.py"]
    R5["tests/providers/test_discovery.py"]
    T1["tests/providers/test_discovery.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    T1 -->|tests| N0
```
