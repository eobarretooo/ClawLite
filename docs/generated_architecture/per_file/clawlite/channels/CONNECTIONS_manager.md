# CONNECTIONS clawlite/channels/manager.py

## Relationship Summary

- Imports 19 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/bus/events.py`
- `clawlite/bus/queue.py`
- `clawlite/channels/base.py`
- `clawlite/channels/dingtalk.py`
- `clawlite/channels/discord.py`
- `clawlite/channels/email.py`
- `clawlite/channels/feishu.py`
- `clawlite/channels/googlechat.py`
- `clawlite/channels/imessage.py`
- `clawlite/channels/irc.py`
- `clawlite/channels/matrix.py`
- `clawlite/channels/mochat.py`
- `clawlite/channels/qq.py`
- `clawlite/channels/signal.py`
- `clawlite/channels/slack.py`
- `clawlite/channels/telegram.py`
- `clawlite/channels/whatsapp.py`
- `clawlite/gateway/tool_approval.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/channels/__init__.py`
- `clawlite/gateway/runtime_builder.py`
- `tests/channels/test_manager.py`

## Matching Tests

- `tests/channels/test_manager.py`

## Mermaid

```mermaid
flowchart TD
    N0["manager.py"]
    D1["clawlite/bus/events.py"]
    D2["clawlite/bus/queue.py"]
    D3["clawlite/channels/base.py"]
    D4["clawlite/channels/dingtalk.py"]
    D5["clawlite/channels/discord.py"]
    D6["clawlite/channels/email.py"]
    D7["clawlite/channels/feishu.py"]
    D8["clawlite/channels/googlechat.py"]
    D9["clawlite/channels/imessage.py"]
    D10["clawlite/channels/irc.py"]
    R1["clawlite/channels/__init__.py"]
    R2["clawlite/gateway/runtime_builder.py"]
    R3["tests/channels/test_manager.py"]
    T1["tests/channels/test_manager.py"]
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
    T1 -->|tests| N0
```
