# READ tests/tools/test_agents_tool.py

## Identity

- Path: `tests/tools/test_agents_tool.py`
- Area: `tests`
- Extension: `.py`
- Lines: 211
- Size bytes: 7870
- SHA1: `85a659466b41908a3c824ec741e3a70fb349e69d`

## Summary

`tests.tools.test_agents_tool` is a Python module in the `tests` area. It defines 3 class(es), led by `FakeMemory`, `FakeProvider`, `FakeTools`. It exposes 9 function(s), including `__init__`, `get_default_model`, `integration_policy`, `_scenario`, `runner`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 7
- Async functions: 2
- Constants: 0
- Internal imports: 4
- Imported by: 0
- Matching tests: 0

## Classes

- `FakeMemory`
- `FakeProvider`
- `FakeTools`

## Functions

- `__init__`
- `get_default_model`
- `integration_policy`
- `schema`
- `test_agents_list_filters_session_and_active_only`
- `test_agents_list_returns_primary_and_subagent_inventory`
- `test_spawn_tool_passes_parent_session_id`
- `_scenario` (async)
- `runner` (async)

## Notable String Markers

- `test_agents_list_filters_session_and_active_only`
- `test_agents_list_returns_primary_and_subagent_inventory`
- `test_spawn_tool_passes_parent_session_id`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_agents_tool.py`.
- Cross-reference `CONNECTIONS_test_agents_tool.md` to see how this file fits into the wider system.
