# READ tests/gateway/test_websocket_handlers.py

## Identity

- Path: `tests/gateway/test_websocket_handlers.py`
- Area: `tests`
- Extension: `.py`
- Lines: 170
- Size bytes: 5871
- SHA1: `920cbdfa0bcbfea3dd161dffefd347356da23031`

## Summary

`tests.gateway.test_websocket_handlers` is a Python module in the `tests` area. It defines 1 class(es), led by `_FakeSocket`. It exposes 9 function(s), including `__init__`, `_build_handler`, `test_websocket_handler_rejects_req_before_connect`, `_stream_result`, `accept`, `receive_json`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 5
- Async functions: 4
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeSocket`

## Functions

- `__init__`
- `_build_handler`
- `test_websocket_handler_rejects_req_before_connect`
- `test_websocket_handler_req_connect_ping_and_catalog`
- `test_websocket_handler_streams_req_chat_chunks_before_final_result`
- `_stream_result` (async)
- `accept` (async)
- `receive_json` (async)
- `send_json` (async)

## Notable String Markers

- `test_websocket_handler_rejects_req_before_connect`
- `test_websocket_handler_req_connect_ping_and_catalog`
- `test_websocket_handler_streams_req_chat_chunks_before_final_result`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/gateway/test_websocket_handlers.py`.
- Cross-reference `CONNECTIONS_test_websocket_handlers.md` to see how this file fits into the wider system.
