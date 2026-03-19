# CONNECTIONS clawlite/cli/onboarding.py

## Relationship Summary

- Imports 10 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/config/loader.py`
- `clawlite/config/schema.py`
- `clawlite/providers/catalog.py`
- `clawlite/providers/codex.py`
- `clawlite/providers/codex_auth.py`
- `clawlite/providers/discovery.py`
- `clawlite/providers/hints.py`
- `clawlite/providers/model_probe.py`
- `clawlite/providers/registry.py`
- `clawlite/workspace/loader.py`

## Reverse Dependencies

- `clawlite/cli/commands.py`
- `clawlite/gateway/server.py`
- `tests/cli/test_configure_wizard.py`
- `tests/cli/test_onboarding.py`

## Matching Tests

- `tests/cli/test_onboarding.py`

## Mermaid

```mermaid
flowchart TD
    N0["onboarding.py"]
    D1["clawlite/config/loader.py"]
    D2["clawlite/config/schema.py"]
    D3["clawlite/providers/catalog.py"]
    D4["clawlite/providers/codex.py"]
    D5["clawlite/providers/codex_auth.py"]
    D6["clawlite/providers/discovery.py"]
    D7["clawlite/providers/hints.py"]
    D8["clawlite/providers/model_probe.py"]
    D9["clawlite/providers/registry.py"]
    D10["clawlite/workspace/loader.py"]
    R1["clawlite/cli/commands.py"]
    R2["clawlite/gateway/server.py"]
    R3["tests/cli/test_configure_wizard.py"]
    R4["tests/cli/test_onboarding.py"]
    T1["tests/cli/test_onboarding.py"]
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
    R4 -->|uses| N0
    T1 -->|tests| N0
```
