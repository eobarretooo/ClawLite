# CONNECTIONS clawlite/channels/base.py

## Relationship Summary

- Imports 4 internal file(s).
- Imported by 20 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/channels/inbound_text.py`
- `clawlite/core/injection_guard.py`
- `clawlite/core/runestone.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/channels/__init__.py`
- `clawlite/channels/dingtalk.py`
- `clawlite/channels/discord.py`
- `clawlite/channels/email.py`
- `clawlite/channels/feishu.py`
- `clawlite/channels/googlechat.py`
- `clawlite/channels/imessage.py`
- `clawlite/channels/irc.py`
- `clawlite/channels/manager.py`
- `clawlite/channels/matrix.py`
- `clawlite/channels/mochat.py`
- `clawlite/channels/qq.py`
- `clawlite/channels/signal.py`
- `clawlite/channels/slack.py`
- `clawlite/channels/telegram.py`
- `clawlite/channels/whatsapp.py`
- `clawlite/gateway/server.py`
- `tests/channels/test_manager.py`
- `tests/channels/test_rate_limiter.py`
- `tests/gateway/test_server.py`

## Mermaid

```mermaid
flowchart TD
    N0["base.py"]
    D1["clawlite/channels/inbound_text.py"]
    D2["clawlite/core/injection_guard.py"]
    D3["clawlite/core/runestone.py"]
    D4["clawlite/utils/logging.py"]
    R1["clawlite/channels/__init__.py"]
    R2["clawlite/channels/dingtalk.py"]
    R3["clawlite/channels/discord.py"]
    R4["clawlite/channels/email.py"]
    R5["clawlite/channels/feishu.py"]
    R6["clawlite/channels/googlechat.py"]
    R7["clawlite/channels/imessage.py"]
    R8["clawlite/channels/irc.py"]
    R9["clawlite/channels/manager.py"]
    R10["clawlite/channels/matrix.py"]
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
    R7 -->|uses| N0
    R8 -->|uses| N0
    R9 -->|uses| N0
    R10 -->|uses| N0
```
