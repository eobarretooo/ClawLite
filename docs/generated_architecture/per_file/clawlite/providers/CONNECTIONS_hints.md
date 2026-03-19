# CONNECTIONS clawlite/providers/hints.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/providers/catalog.py`

## Reverse Dependencies

- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/gateway/payloads.py`
- `tests/providers/test_hints.py`

## Matching Tests

- `tests/providers/test_hints.py`

## Mermaid

```mermaid
flowchart TD
    N0["hints.py"]
    D1["clawlite/providers/catalog.py"]
    R1["clawlite/cli/onboarding.py"]
    R2["clawlite/cli/ops.py"]
    R3["clawlite/gateway/payloads.py"]
    R4["tests/providers/test_hints.py"]
    T1["tests/providers/test_hints.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
```
