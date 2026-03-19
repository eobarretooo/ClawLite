# CONNECTIONS clawlite/providers/litellm.py

## Relationship Summary

- Imports 4 internal file(s).
- Imported by 6 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/core/engine.py`
- `clawlite/providers/base.py`
- `clawlite/providers/reliability.py`
- `clawlite/providers/telemetry.py`

## Reverse Dependencies

- `clawlite/providers/custom.py`
- `clawlite/providers/registry.py`
- `tests/providers/test_litellm_anthropic.py`
- `tests/providers/test_litellm_retry.py`
- `tests/providers/test_registry_auth_resolution.py`
- `tests/providers/test_streaming_recovery.py`

## Matching Tests

- `tests/providers/test_litellm_anthropic.py`
- `tests/providers/test_litellm_retry.py`

## Mermaid

```mermaid
flowchart TD
    N0["litellm.py"]
    D1["clawlite/core/engine.py"]
    D2["clawlite/providers/base.py"]
    D3["clawlite/providers/reliability.py"]
    D4["clawlite/providers/telemetry.py"]
    R1["clawlite/providers/custom.py"]
    R2["clawlite/providers/registry.py"]
    R3["tests/providers/test_litellm_anthropic.py"]
    R4["tests/providers/test_litellm_retry.py"]
    R5["tests/providers/test_registry_auth_resolution.py"]
    R6["tests/providers/test_streaming_recovery.py"]
    T1["tests/providers/test_litellm_anthropic.py"]
    T2["tests/providers/test_litellm_retry.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
