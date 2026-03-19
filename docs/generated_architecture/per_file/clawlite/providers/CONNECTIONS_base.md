# CONNECTIONS clawlite/providers/base.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 8 internal file(s).
- Matched test files: 0.

## Reverse Dependencies

- `clawlite/providers/__init__.py`
- `clawlite/providers/codex.py`
- `clawlite/providers/failover.py`
- `clawlite/providers/litellm.py`
- `clawlite/providers/registry.py`
- `tests/gateway/test_server.py`
- `tests/providers/test_failover.py`
- `tests/tools/test_skill_tool.py`

## Mermaid

```mermaid
flowchart TD
    N0["base.py"]
    R1["clawlite/providers/__init__.py"]
    R2["clawlite/providers/codex.py"]
    R3["clawlite/providers/failover.py"]
    R4["clawlite/providers/litellm.py"]
    R5["clawlite/providers/registry.py"]
    R6["tests/gateway/test_server.py"]
    R7["tests/providers/test_failover.py"]
    R8["tests/tools/test_skill_tool.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    R7 -->|uses| N0
    R8 -->|uses| N0
```
