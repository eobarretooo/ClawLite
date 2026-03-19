# READ tests/tools/test_browser_tool.py

## Identity

- Path: `tests/tools/test_browser_tool.py`
- Area: `tests`
- Extension: `.py`
- Lines: 196
- Size bytes: 6835
- SHA1: `a063edc02889ddf011a510d19c07cbe8907fbe54`

## Summary

`tests.tools.test_browser_tool` is a Python module in the `tests` area. It defines 6 class(es), led by `FakeBrowser`, `FakeChromium`, `FakePage`, `FakePlaywrightManager`. It exposes 19 function(s), including `__init__`, `_install_fake_playwright`, `is_closed`, `__aenter__`, `__aexit__`, `_fake_resolve`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 6
- Functions: 4
- Async functions: 15
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `FakeBrowser`
- `FakeChromium`
- `FakePage`
- `FakePlaywrightManager`
- `FakePlaywrightRuntime`
- `FakeResponse`

## Functions

- `__init__`
- `_install_fake_playwright`
- `is_closed`
- `set_default_timeout`
- `__aenter__` (async)
- `__aexit__` (async)
- `_fake_resolve` (async)
- `close` (async)
- `goto` (async)
- `inner_text` (async)
- `launch` (async)
- `new_page` (async)
- `start` (async)
- `stop` (async)
- `test_browser_tool_blocks_private_or_local_targets` (async)
- `test_browser_tool_closes_page_browser_and_playwright` (async)
- `test_browser_tool_respects_allowlist` (async)
- `test_browser_tool_returns_setup_hint_and_cleans_playwright_on_launch_failure` (async)
- `title` (async)

## Notable String Markers

- `test_browser_tool_blocks_private_or_local_targets`
- `test_browser_tool_closes_page_browser_and_playwright`
- `test_browser_tool_respects_allowlist`
- `test_browser_tool_returns_setup_hint_and_cleans_playwright_on_launch_failure`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_browser_tool.py`.
- Cross-reference `CONNECTIONS_test_browser_tool.md` to see how this file fits into the wider system.
