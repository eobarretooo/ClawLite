# CONNECTIONS clawlite/gateway/tool_approval.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/bus/events.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/channels/manager.py`
- `clawlite/gateway/runtime_builder.py`
- `tests/gateway/test_tool_approval.py`

## Matching Tests

- `tests/gateway/test_tool_approval.py`

## Mermaid

```mermaid
flowchart TD
    N0["tool_approval.py"]
    D1["clawlite/bus/events.py"]
    D2["clawlite/utils/logging.py"]
    R1["clawlite/channels/manager.py"]
    R2["clawlite/gateway/runtime_builder.py"]
    R3["tests/gateway/test_tool_approval.py"]
    T1["tests/gateway/test_tool_approval.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
