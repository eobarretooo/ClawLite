# CONNECTIONS clawlite/workspace/loader.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 12 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/workspace/user_profile.py`

## Reverse Dependencies

- `clawlite/cli/commands.py`
- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/core/prompt.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/workspace/__init__.py`
- `clawlite/workspace/bootstrap.py`
- `clawlite/workspace/identity_enforcer.py`
- `tests/cli/test_commands.py`
- `tests/gateway/test_server.py`
- `tests/workspace/test_user_profile.py`
- `tests/workspace/test_workspace_loader.py`

## Matching Tests

- `tests/config/test_loader.py`
- `tests/workspace/test_workspace_loader.py`

## Mermaid

```mermaid
flowchart TD
    N0["loader.py"]
    D1["clawlite/workspace/user_profile.py"]
    R1["clawlite/cli/commands.py"]
    R2["clawlite/cli/onboarding.py"]
    R3["clawlite/cli/ops.py"]
    R4["clawlite/core/prompt.py"]
    R5["clawlite/gateway/runtime_builder.py"]
    R6["clawlite/workspace/__init__.py"]
    R7["clawlite/workspace/bootstrap.py"]
    R8["clawlite/workspace/identity_enforcer.py"]
    R9["tests/cli/test_commands.py"]
    R10["tests/gateway/test_server.py"]
    T1["tests/config/test_loader.py"]
    T2["tests/workspace/test_workspace_loader.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    R7 -->|uses| N0
    R8 -->|uses| N0
    R9 -->|uses| N0
    R10 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
