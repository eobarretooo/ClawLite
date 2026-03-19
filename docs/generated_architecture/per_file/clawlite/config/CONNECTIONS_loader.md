# CONNECTIONS clawlite/config/loader.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 14 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/config/schema.py`

## Reverse Dependencies

- `clawlite/cli/commands.py`
- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/config/__init__.py`
- `clawlite/config/watcher.py`
- `clawlite/core/skills.py`
- `clawlite/gateway/server.py`
- `clawlite/tools/skill.py`
- `clawlite/workspace/bootstrap.py`
- `tests/cli/test_commands.py`
- `tests/config/test_loader.py`
- `tests/config/test_schema.py`
- `tests/config/test_watcher.py`
- `tests/workspace/test_workspace_loader.py`

## Matching Tests

- `tests/config/test_loader.py`
- `tests/workspace/test_workspace_loader.py`

## Mermaid

```mermaid
flowchart TD
    N0["loader.py"]
    D1["clawlite/config/schema.py"]
    R1["clawlite/cli/commands.py"]
    R2["clawlite/cli/onboarding.py"]
    R3["clawlite/cli/ops.py"]
    R4["clawlite/config/__init__.py"]
    R5["clawlite/config/watcher.py"]
    R6["clawlite/core/skills.py"]
    R7["clawlite/gateway/server.py"]
    R8["clawlite/tools/skill.py"]
    R9["clawlite/workspace/bootstrap.py"]
    R10["tests/cli/test_commands.py"]
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
