# READ clawlite/jobs/queue.py

## Identity

- Path: `clawlite/jobs/queue.py`
- Area: `jobs`
- Extension: `.py`
- Lines: 295
- Size bytes: 10107
- SHA1: `dd0d0111d124723827cbcacb4eb75c7d9d3afd9c`

## Summary

`clawlite.jobs.queue` is a Python module in the `jobs` area. It defines 2 class(es), led by `Job`, `JobQueue`. It exposes 19 function(s), including `__init__`, `_owned_job`, `_pop_pending`, `_run_job`, `_worker_loop`, `stop`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 16
- Async functions: 3
- Constants: 1
- Internal imports: 0
- Imported by: 8
- Matching tests: 3

## Classes

- `Job`
- `JobQueue`

## Functions

- `__init__`
- `_owned_job`
- `_pop_pending`
- `_resolve_worker`
- `_utc_now`
- `cancel`
- `einherjar`
- `is_einherjar`
- `list_jobs`
- `register_custom`
- `restore_from_journal`
- `set_journal`
- `start`
- `status`
- `submit`
- `worker_status`
- `_run_job` (async)
- `_worker_loop` (async)
- `stop` (async)

## Constants

- `EINHERJAR_PRIORITY`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/jobs/queue.py`.
- Cross-reference `CONNECTIONS_queue.md` to see how this file fits into the wider system.
