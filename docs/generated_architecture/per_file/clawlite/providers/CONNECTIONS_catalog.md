# CONNECTIONS clawlite/providers/catalog.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 5 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/gateway/server.py`
- `clawlite/providers/hints.py`
- `tests/providers/test_catalog.py`

## Matching Tests

- `tests/providers/test_catalog.py`

## Mermaid

```mermaid
flowchart TD
    N0["catalog.py"]
    R1["clawlite/cli/onboarding.py"]
    R2["clawlite/cli/ops.py"]
    R3["clawlite/gateway/server.py"]
    R4["clawlite/providers/hints.py"]
    R5["tests/providers/test_catalog.py"]
    T1["tests/providers/test_catalog.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    T1 -->|tests| N0
```
