# CONNECTIONS tests/core/test_engine.py

## Relationship Summary

- Imports 11 internal file(s).
- Imported by 0 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/config/schema.py`
- `clawlite/core/engine.py`
- `clawlite/core/memory.py`
- `clawlite/core/prompt.py`
- `clawlite/core/subagent.py`
- `clawlite/core/subagent_synthesizer.py`
- `clawlite/runtime/telemetry.py`
- `clawlite/session/store.py`
- `clawlite/tools/base.py`
- `clawlite/tools/registry.py`
- `clawlite/utils/logging.py`

## Candidate Sources Exercised By This Test File

- `clawlite/core/engine.py`
- `clawlite/gateway/engine_diagnostics.py`

## Mermaid

```mermaid
flowchart TD
    N0["test_engine.py"]
    D1["clawlite/config/schema.py"]
    D2["clawlite/core/engine.py"]
    D3["clawlite/core/memory.py"]
    D4["clawlite/core/prompt.py"]
    D5["clawlite/core/subagent.py"]
    D6["clawlite/core/subagent_synthesizer.py"]
    D7["clawlite/runtime/telemetry.py"]
    D8["clawlite/session/store.py"]
    D9["clawlite/tools/base.py"]
    D10["clawlite/tools/registry.py"]
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
```
