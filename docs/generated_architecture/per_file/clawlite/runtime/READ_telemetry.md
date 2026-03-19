# READ clawlite/runtime/telemetry.py

## Identity

- Path: `clawlite/runtime/telemetry.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 130
- Size bytes: 3902
- SHA1: `a36302dfaf895df9405bd0168d52fdfd040b828f`

## Summary

`clawlite.runtime.telemetry` is a Python module in the `runtime` area. It defines 2 class(es), led by `_NoopSpan`, `_NoopTracer`. It exposes 10 function(s), including `__enter__`, `__exit__`, `configure_observability`. It depends on 3 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 10
- Async functions: 0
- Constants: 3
- Internal imports: 0
- Imported by: 6
- Matching tests: 2

## Classes

- `_NoopSpan`
- `_NoopTracer`

## Functions

- `__enter__`
- `__exit__`
- `configure_observability`
- `get_tracer`
- `record_exception`
- `set_attribute`
- `set_span_attributes`
- `set_test_tracer_factory`
- `start_as_current_span`
- `telemetry_status`

## Constants

- `_NOOP_TRACER`
- `_TELEMETRY_STATUS`
- `_TRACER_FACTORY`

## Notable String Markers

- `test_tracer_factory`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/telemetry.py`.
- Cross-reference `CONNECTIONS_telemetry.md` to see how this file fits into the wider system.
