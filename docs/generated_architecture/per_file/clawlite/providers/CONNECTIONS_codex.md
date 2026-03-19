# CONNECTIONS clawlite/providers/codex.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 5 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/providers/base.py`
- `clawlite/providers/reliability.py`

## Reverse Dependencies

- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/providers/registry.py`
- `tests/providers/test_codex_retry.py`
- `tests/providers/test_registry_auth_resolution.py`

## Matching Tests

- `tests/providers/test_codex_retry.py`

## Mermaid

```mermaid
flowchart TD
    N0["codex.py"]
    D1["clawlite/providers/base.py"]
    D2["clawlite/providers/reliability.py"]
    R1["clawlite/cli/onboarding.py"]
    R2["clawlite/cli/ops.py"]
    R3["clawlite/providers/registry.py"]
    R4["tests/providers/test_codex_retry.py"]
    R5["tests/providers/test_registry_auth_resolution.py"]
    T1["tests/providers/test_codex_retry.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    T1 -->|tests| N0
```
