# READ clawlite/channels/base.py

## Identity

- Path: `clawlite/channels/base.py`
- Area: `channels`
- Extension: `.py`
- Lines: 154
- Size bytes: 5054
- SHA1: `e32460d16962d13289c4479dd8c48dd7f1f8d6ef`

## Summary

`clawlite.channels.base` is a Python module in the `channels` area. It defines 5 class(es), led by `BaseChannel`, `ChannelCapabilities`, `ChannelHealth`, `PassiveChannel`. It exposes 11 function(s), including `__init__`, `allow`, `capabilities`, `cancel_task`, `emit`, `send`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 5
- Functions: 6
- Async functions: 5
- Constants: 1
- Internal imports: 4
- Imported by: 20
- Matching tests: 0

## Classes

- `BaseChannel`
- `ChannelCapabilities`
- `ChannelHealth`
- `PassiveChannel`
- `_TokenBucketRateLimiter`

## Functions

- `__init__`
- `allow`
- `capabilities`
- `health`
- `reset`
- `running`
- `cancel_task` (async)
- `emit` (async)
- `send` (async)
- `start` (async)
- `stop` (async)

## Constants

- `_CHANNEL_RATE_LIMITER`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/base.py`.
- Cross-reference `CONNECTIONS_base.md` to see how this file fits into the wider system.
