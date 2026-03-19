# CONNECTIONS clawlite/tools/mcp.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/config/schema.py`
- `clawlite/tools/base.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/tools/test_health_check.py`
- `tests/tools/test_mcp.py`

## Matching Tests

- `tests/tools/test_cron_message_spawn_mcp.py`
- `tests/tools/test_mcp.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["mcp.py"]
    D1["clawlite/config/schema.py"]
    D2["clawlite/tools/base.py"]
    D3["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/tools/test_health_check.py"]
    R3["tests/tools/test_mcp.py"]
    T1["tests/tools/test_cron_message_spawn_mcp.py"]
    T2["tests/tools/test_mcp.py"]
    T3["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
