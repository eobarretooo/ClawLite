# CONNECTIONS clawlite/workspace/identity_enforcer.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/workspace/loader.py`
- `clawlite/workspace/user_profile.py`

## Reverse Dependencies

- `clawlite/core/engine.py`
- `tests/workspace/test_user_profile.py`

## Mermaid

```mermaid
flowchart TD
    N0["identity_enforcer.py"]
    D1["clawlite/workspace/loader.py"]
    D2["clawlite/workspace/user_profile.py"]
    R1["clawlite/core/engine.py"]
    R2["tests/workspace/test_user_profile.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
```
