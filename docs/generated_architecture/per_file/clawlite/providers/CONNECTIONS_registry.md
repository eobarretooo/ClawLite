# CONNECTIONS clawlite/providers/registry.py

## Relationship Summary

- Imports 9 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/providers/base.py`
- `clawlite/providers/codex.py`
- `clawlite/providers/codex_auth.py`
- `clawlite/providers/custom.py`
- `clawlite/providers/discovery.py`
- `clawlite/providers/failover.py`
- `clawlite/providers/gemini_auth.py`
- `clawlite/providers/litellm.py`
- `clawlite/providers/qwen_auth.py`

## Reverse Dependencies

- `clawlite/cli/onboarding.py`
- `clawlite/cli/ops.py`
- `clawlite/providers/__init__.py`
- `tests/providers/test_registry_auth_resolution.py`

## Matching Tests

- `tests/providers/test_registry_auth_resolution.py`
- `tests/tools/test_registry.py`

## Mermaid

```mermaid
flowchart TD
    N0["registry.py"]
    D1["clawlite/providers/base.py"]
    D2["clawlite/providers/codex.py"]
    D3["clawlite/providers/codex_auth.py"]
    D4["clawlite/providers/custom.py"]
    D5["clawlite/providers/discovery.py"]
    D6["clawlite/providers/failover.py"]
    D7["clawlite/providers/gemini_auth.py"]
    D8["clawlite/providers/litellm.py"]
    D9["clawlite/providers/qwen_auth.py"]
    R1["clawlite/cli/onboarding.py"]
    R2["clawlite/cli/ops.py"]
    R3["clawlite/providers/__init__.py"]
    R4["tests/providers/test_registry_auth_resolution.py"]
    T1["tests/providers/test_registry_auth_resolution.py"]
    T2["tests/tools/test_registry.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    N0 -->|imports| D5
    N0 -->|imports| D6
    N0 -->|imports| D7
    N0 -->|imports| D8
    N0 -->|imports| D9
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
