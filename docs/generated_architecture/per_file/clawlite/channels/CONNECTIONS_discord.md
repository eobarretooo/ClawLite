# CONNECTIONS clawlite/channels/discord.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/channels/base.py`

## Reverse Dependencies

- `clawlite/channels/manager.py`
- `tests/channels/test_discord.py`
- `tests/channels/test_outbound_adapters.py`

## Matching Tests

- `tests/channels/test_discord.py`
- `tests/gateway/test_discord_thread_binding.py`
- `tests/tools/test_discord_admin_tool.py`

## Mermaid

```mermaid
flowchart TD
    N0["discord.py"]
    D1["clawlite/channels/base.py"]
    R1["clawlite/channels/manager.py"]
    R2["tests/channels/test_discord.py"]
    R3["tests/channels/test_outbound_adapters.py"]
    T1["tests/channels/test_discord.py"]
    T2["tests/gateway/test_discord_thread_binding.py"]
    T3["tests/tools/test_discord_admin_tool.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
