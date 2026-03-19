# CONNECTIONS clawlite/gateway/discord_thread_binding.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/bus/events.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/gateway/test_discord_thread_binding.py`

## Matching Tests

- `tests/channels/test_discord.py`
- `tests/gateway/test_discord_thread_binding.py`

## Mermaid

```mermaid
flowchart TD
    N0["discord_thread_binding.py"]
    D1["clawlite/bus/events.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/gateway/test_discord_thread_binding.py"]
    T1["tests/channels/test_discord.py"]
    T2["tests/gateway/test_discord_thread_binding.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
