# READ tests/channels/test_irc.py

## Identity

- Path: `tests/channels/test_irc.py`
- Area: `tests`
- Extension: `.py`
- Lines: 103
- Size bytes: 2923
- SHA1: `cc0f8df37094c520c3113026c124b71048923999`

## Summary

`tests.channels.test_irc` is a Python module in the `tests` area. It defines 2 class(es), led by `_FakeReader`, `_FakeWriter`. It exposes 10 function(s), including `__init__`, `close`, `test_irc_channel_connects_joins_responds_to_ping_and_emits_privmsg`, `_on_message`, `_open_connection`, `_scenario`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 4
- Async functions: 6
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeReader`
- `_FakeWriter`

## Functions

- `__init__`
- `close`
- `test_irc_channel_connects_joins_responds_to_ping_and_emits_privmsg`
- `write`
- `_on_message` (async)
- `_open_connection` (async)
- `_scenario` (async)
- `drain` (async)
- `readline` (async)
- `wait_closed` (async)

## Notable String Markers

- `clawlite :hello`
- `clawlite :reply`
- `test_irc_channel_connects_joins_responds_to_ping_and_emits_privmsg`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/channels/test_irc.py`.
- Cross-reference `CONNECTIONS_test_irc.md` to see how this file fits into the wider system.
