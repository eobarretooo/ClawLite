# READ tests/core/test_memory_resources_helpers.py

## Identity

- Path: `tests/core/test_memory_resources_helpers.py`
- Area: `tests`
- Extension: `.py`
- Lines: 107
- Size bytes: 3431
- SHA1: `1969a98922ecf65e081698c10e6de60393551a05`

## Summary

`tests.core.test_memory_resources_helpers` is a Python module in the `tests` area. It defines 3 class(es), led by `_Backend`, `_Record`, `_Resource`. It exposes 11 function(s), including `__init__`, `delete_layer_records`, `delete_ttl_entries`. It depends on 3 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 11
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_Backend`
- `_Record`
- `_Resource`

## Functions

- `__init__`
- `delete_layer_records`
- `delete_ttl_entries`
- `fetch_all_resources`
- `fetch_expired_record_ids`
- `fetch_layer_records`
- `fetch_records_by_resource`
- `fetch_resource`
- `test_purge_expired_records_deletes_layers_and_ttl_entries`
- `test_resource_helpers_round_trip_and_lookup_records`
- `upsert_resource`

## Notable String Markers

- `test_purge_expired_records_deletes_layers_and_ttl_entries`
- `test_resource_helpers_round_trip_and_lookup_records`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_memory_resources_helpers.py`.
- Cross-reference `CONNECTIONS_test_memory_resources_helpers.md` to see how this file fits into the wider system.
