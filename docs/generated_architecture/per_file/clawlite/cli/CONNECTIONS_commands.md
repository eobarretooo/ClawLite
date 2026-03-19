# CONNECTIONS clawlite/cli/commands.py

## Relationship Summary

- Imports 11 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/__init__.py`
- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/config/loader.py`
- `clawlite/core/skills.py`
- `clawlite/gateway/server.py`
- `clawlite/jobs/journal.py`
- `clawlite/scheduler/cron.py`
- `clawlite/tools/registry.py`
- `clawlite/utils/logger.py`
- `clawlite/workspace/loader.py`

## Reverse Dependencies

- `clawlite/cli/__init__.py`
- `tests/cli/test_commands.py`
- `tests/cli/test_configure_wizard.py`

## Matching Tests

- `tests/cli/test_commands.py`

## Mermaid

```mermaid
flowchart TD
    N0["commands.py"]
    D1["clawlite/__init__.py"]
    D2["clawlite/cli/onboarding.py"]
    D3["clawlite/cli/ops.py"]
    D4["clawlite/config/loader.py"]
    D5["clawlite/core/skills.py"]
    D6["clawlite/gateway/server.py"]
    D7["clawlite/jobs/journal.py"]
    D8["clawlite/scheduler/cron.py"]
    D9["clawlite/tools/registry.py"]
    D10["clawlite/utils/logger.py"]
    R1["clawlite/cli/__init__.py"]
    R2["tests/cli/test_commands.py"]
    R3["tests/cli/test_configure_wizard.py"]
    T1["tests/cli/test_commands.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    N0 -->|imports| D5
    N0 -->|imports| D6
    N0 -->|imports| D7
    N0 -->|imports| D8
    N0 -->|imports| D9
    N0 -->|imports| D10
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
