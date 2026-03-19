# READ clawlite/providers/registry.py

## Identity

- Path: `clawlite/providers/registry.py`
- Area: `providers`
- Extension: `.py`
- Lines: 934
- Size bytes: 34235
- SHA1: `4e20d7a2ab6ea7018c8f19a1c060a22d69275cf5`

## Summary

`clawlite.providers.registry` is a Python module in the `providers` area. It defines 2 class(es), led by `ProviderResolution`, `ProviderSpec`. It exposes 25 function(s), including `_add`, `_build_provider_single`, `_cfg_value`. It depends on 13 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 25
- Async functions: 0
- Constants: 2
- Internal imports: 9
- Imported by: 4
- Matching tests: 2

## Classes

- `ProviderResolution`
- `ProviderSpec`

## Functions

- `_add`
- `_build_provider_single`
- `_cfg_value`
- `_configured_provider_hint`
- `_fallback_models`
- `_find_gateway`
- `_find_spec`
- `_is_compatible_key_for_spec`
- `_normalize`
- `_normalize_model_for_provider`
- `_provider_cfg`
- `_reliability_settings`
- `_resolve_api_key`
- `_resolve_base_url`
- `_resolve_codex_oauth`
- `_resolve_gemini_oauth`
- `_resolve_generic_oauth`
- `_resolve_qwen_oauth`
- `_spec_from_api_key`
- `_spec_from_base_url`
- `_spec_from_model`
- `_spec_names`
- `build_provider`
- `detect_provider_name`
- `resolve_litellm_provider`

## Constants

- `OPENAI_DEFAULT_BASE_URL`
- `SPECS`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/providers/registry.py`.
- Cross-reference `CONNECTIONS_registry.md` to see how this file fits into the wider system.
