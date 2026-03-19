# READ tests/jobs/test_queue.py

## Identity

- Path: `tests/jobs/test_queue.py`
- Area: `tests`
- Extension: `.py`
- Lines: 177
- Size bytes: 5013
- SHA1: `c50e659617bb51137b9de30c7789beb907cdcbe4`

## Summary

`tests.jobs.test_queue` is a Python module in the `tests` area. It exposes 11 function(s), including `queue`, `flaky_worker`, `test_cancel_queued_job`, `test_cancel_running_job_marks_cancelled`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 1
- Async functions: 10
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `queue`
- `flaky_worker` (async)
- `test_cancel_queued_job` (async)
- `test_cancel_running_job_marks_cancelled` (async)
- `test_job_lifecycle_done` (async)
- `test_job_retry_on_failure` (async)
- `test_list_jobs_by_session` (async)
- `test_priority_ordering` (async)
- `test_status_and_cancel_respect_session_scope` (async)
- `test_submit_and_status` (async)
- `worker` (async)

## Notable String Markers

- `test_cancel_queued_job`
- `test_cancel_running_job_marks_cancelled`
- `test_job_lifecycle_done`
- `test_job_retry_on_failure`
- `test_list_jobs_by_session`
- `test_priority_ordering`
- `test_status_and_cancel_respect_session_scope`
- `test_submit_and_status`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/jobs/test_queue.py`.
- Cross-reference `CONNECTIONS_test_queue.md` to see how this file fits into the wider system.
