# READ clawlite/gateway/runtime_builder.py

## Identity

- Path: `clawlite/gateway/runtime_builder.py`
- Area: `gateway`
- Extension: `.py`
- Lines: 634
- Size bytes: 27649
- SHA1: `a3dbf0fda4e46c9946fdb332e6f4d31cdf935586`

## Summary

`clawlite.gateway.runtime_builder` is a Python module in the `gateway` area. It defines 3 class(es), led by `RuntimeContainer`, `_CronAPI`, `_MessageAPI`. It exposes 18 function(s), including `__init__`, `_provider_config`, `_provider_probe_candidates`, `_channel_inbound_interceptor`, `_evo_notify`, `_evo_run_llm`. It depends on 50 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 9
- Async functions: 9
- Constants: 0
- Internal imports: 46
- Imported by: 2
- Matching tests: 0

## Classes

- `RuntimeContainer`
- `_CronAPI`
- `_MessageAPI`

## Functions

- `__init__`
- `_provider_config`
- `_provider_probe_candidates`
- `_resume_runner_factory`
- `_validate_local_provider_runtime`
- `build_runtime`
- `enable_job`
- `list_jobs`
- `remove_job`
- `_channel_inbound_interceptor` (async)
- `_evo_notify` (async)
- `_evo_run_llm` (async)
- `_resume_runner` (async)
- `_session_runner` (async)
- `_subagent_runner` (async)
- `add_job` (async)
- `run_job` (async)
- `send` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/gateway/runtime_builder.py`.
- Cross-reference `CONNECTIONS_runtime_builder.md` to see how this file fits into the wider system.
