# CONNECTIONS clawlite/tools/agents.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/core/subagent.py`
- `clawlite/tools/base.py`
- `clawlite/tools/sessions.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/tools/test_agents_tool.py`

## Matching Tests

- `tests/gateway/test_subagents_runtime.py`
- `tests/tools/test_agents_tool.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["agents.py"]
    D1["clawlite/core/subagent.py"]
    D2["clawlite/tools/base.py"]
    D3["clawlite/tools/sessions.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/tools/test_agents_tool.py"]
    T1["tests/gateway/test_subagents_runtime.py"]
    T2["tests/tools/test_agents_tool.py"]
    T3["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
