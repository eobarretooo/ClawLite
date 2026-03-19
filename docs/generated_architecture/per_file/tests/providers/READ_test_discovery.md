# READ tests/providers/test_discovery.py

## Identity

- Path: `tests/providers/test_discovery.py`
- Area: `tests`
- Extension: `.py`
- Lines: 167
- Size bytes: 6175
- SHA1: `dedc1ae0f9edc546f9f2d0412fcf19d8831a5d5f`

## Summary

`tests.providers.test_discovery` is a Python module in the `tests` area. It defines 2 class(es), led by `_Client`, `_Response`. It exposes 13 function(s), including `__enter__`, `__exit__`, `__init__`. It depends on 2 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 13
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_Client`
- `_Response`

## Functions

- `__enter__`
- `__exit__`
- `__init__`
- `get`
- `json`
- `post`
- `test_detect_local_runtime_distinguishes_ollama_and_vllm`
- `test_detect_local_runtime_does_not_assume_generic_loopback_is_vllm`
- `test_normalize_local_runtime_base_url_preserves_reverse_proxy_prefix`
- `test_probe_local_provider_runtime_accepts_ollama_show_fallback`
- `test_probe_local_provider_runtime_preserves_ollama_reverse_proxy_prefix`
- `test_probe_local_provider_runtime_preserves_vllm_reverse_proxy_prefix`
- `test_probe_local_provider_runtime_rejects_missing_vllm_model`

## Notable String Markers

- `test_detect_local_runtime_distinguishes_ollama_and_vllm`
- `test_detect_local_runtime_does_not_assume_generic_loopback_is_vllm`
- `test_normalize_local_runtime_base_url_preserves_reverse_proxy_prefix`
- `test_probe_local_provider_runtime_accepts_ollama_show_fallback`
- `test_probe_local_provider_runtime_preserves_ollama_reverse_proxy_prefix`
- `test_probe_local_provider_runtime_preserves_vllm_reverse_proxy_prefix`
- `test_probe_local_provider_runtime_rejects_missing_vllm_model`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/providers/test_discovery.py`.
- Cross-reference `CONNECTIONS_test_discovery.md` to see how this file fits into the wider system.
