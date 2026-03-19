# READ clawlite/tools/browser.py

## Identity

- Path: `clawlite/tools/browser.py`
- Area: `tools`
- Extension: `.py`
- Lines: 210
- Size bytes: 8983
- SHA1: `b278e46bb33d82298efc59b98f0d1594e1e3047b`

## Summary

`clawlite.tools.browser` is a Python module in the `tools` area. It defines 1 class(es), led by `BrowserTool`. It exposes 10 function(s), including `__init__`, `_format_untrusted_browser_content`, `_playwright_setup_hint`, `_close_runtime`, `_ensure_browser`, `_ensure_page`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 4
- Async functions: 6
- Constants: 1
- Internal imports: 2
- Imported by: 3
- Matching tests: 2

## Classes

- `BrowserTool`

## Functions

- `__init__`
- `_format_untrusted_browser_content`
- `_playwright_setup_hint`
- `args_schema`
- `_close_runtime` (async)
- `_ensure_browser` (async)
- `_ensure_page` (async)
- `_validate_target` (async)
- `health_check` (async)
- `run` (async)

## Constants

- `_UNTRUSTED_BROWSER_CONTENT_NOTICE`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/browser.py`.
- Cross-reference `CONNECTIONS_browser.md` to see how this file fits into the wider system.
