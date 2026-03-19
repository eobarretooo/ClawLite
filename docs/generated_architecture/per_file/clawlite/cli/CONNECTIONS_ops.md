# CONNECTIONS clawlite/cli/ops.py

## Relationship Summary

- Imports 16 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/channels/telegram_pairing.py`
- `clawlite/config/loader.py`
- `clawlite/config/schema.py`
- `clawlite/core/memory.py`
- `clawlite/core/memory_monitor.py`
- `clawlite/providers/catalog.py`
- `clawlite/providers/codex.py`
- `clawlite/providers/codex_auth.py`
- `clawlite/providers/discovery.py`
- `clawlite/providers/gemini_auth.py`
- `clawlite/providers/hints.py`
- `clawlite/providers/model_probe.py`
- `clawlite/providers/qwen_auth.py`
- `clawlite/providers/registry.py`
- `clawlite/providers/reliability.py`
- `clawlite/workspace/loader.py`

## Reverse Dependencies

- `clawlite/cli/commands.py`
- `clawlite/gateway/server.py`
- `clawlite/tools/skill.py`
- `tests/cli/test_commands.py`

## Mermaid

```mermaid
flowchart TD
    N0["ops.py"]
    D1["clawlite/channels/telegram_pairing.py"]
    D2["clawlite/config/loader.py"]
    D3["clawlite/config/schema.py"]
    D4["clawlite/core/memory.py"]
    D5["clawlite/core/memory_monitor.py"]
    D6["clawlite/providers/catalog.py"]
    D7["clawlite/providers/codex.py"]
    D8["clawlite/providers/codex_auth.py"]
    D9["clawlite/providers/discovery.py"]
    D10["clawlite/providers/gemini_auth.py"]
    R1["clawlite/cli/commands.py"]
    R2["clawlite/gateway/server.py"]
    R3["clawlite/tools/skill.py"]
    R4["tests/cli/test_commands.py"]
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
```
