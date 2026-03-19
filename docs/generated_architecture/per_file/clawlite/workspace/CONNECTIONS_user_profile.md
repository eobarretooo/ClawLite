# CONNECTIONS clawlite/workspace/user_profile.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/workspace/identity_enforcer.py`
- `clawlite/workspace/loader.py`
- `tests/workspace/test_user_profile.py`

## Matching Tests

- `tests/workspace/test_user_profile.py`

## Mermaid

```mermaid
flowchart TD
    N0["user_profile.py"]
    R1["clawlite/workspace/identity_enforcer.py"]
    R2["clawlite/workspace/loader.py"]
    R3["tests/workspace/test_user_profile.py"]
    T1["tests/workspace/test_user_profile.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
