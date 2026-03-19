# READ tests/gateway/test_memory_dashboard.py

## Identity

- Path: `tests/gateway/test_memory_dashboard.py`
- Area: `tests`
- Extension: `.py`
- Lines: 65
- Size bytes: 2365
- SHA1: `ec3b32bb820b1e236dba238e5839db49d209ad2b`

## Summary

`tests.gateway.test_memory_dashboard` is a Python module in the `tests` area. It defines 3 class(es), led by `_BrokenMonitor`, `_FakeMemoryStore`, `_FakeMonitor`. It exposes 6 function(s), including `analysis_stats`, `quality_state_snapshot`, `telemetry`. It depends on 3 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 6
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_BrokenMonitor`
- `_FakeMemoryStore`
- `_FakeMonitor`

## Functions

- `analysis_stats`
- `quality_state_snapshot`
- `telemetry`
- `test_dashboard_memory_summary_fail_soft_when_monitor_errors`
- `test_dashboard_memory_summary_includes_all_sections`
- `test_memory_dashboard_helpers_collect_analysis_and_quality`

## Notable String Markers

- `test_dashboard_memory_summary_fail_soft_when_monitor_errors`
- `test_dashboard_memory_summary_includes_all_sections`
- `test_memory_dashboard_helpers_collect_analysis_and_quality`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/gateway/test_memory_dashboard.py`.
- Cross-reference `CONNECTIONS_test_memory_dashboard.md` to see how this file fits into the wider system.
