# CONNECTIONS clawlite/providers/model_probe.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `tests/providers/test_model_probe.py`

## Matching Tests

- `tests/providers/test_model_probe.py`

## Mermaid

```mermaid
flowchart TD
    N0["model_probe.py"]
    R1["clawlite/cli/onboarding.py"]
    R2["clawlite/cli/ops.py"]
    R3["tests/providers/test_model_probe.py"]
    T1["tests/providers/test_model_probe.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
