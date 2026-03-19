# READ clawlite/core/skills.py

## Identity

- Path: `clawlite/core/skills.py`
- Area: `core`
- Extension: `.py`
- Lines: 1362
- Size bytes: 53033
- SHA1: `58fd5512ccf2bc5e3ca2a6a9e06119327f83b46d`

## Summary

`clawlite.core.skills` is a Python module in the `core` area. It defines 2 class(es), led by `SkillSpec`, `SkillsLoader`. It exposes 68 function(s), including `__init__`, `_atomic_write_state`, `_build_execution_contract`, `_loop`, `_watcher_loop_poll`, `_watcher_loop_watchfiles`. It depends on 18 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 62
- Async functions: 6
- Constants: 4
- Internal imports: 1
- Imported by: 8
- Matching tests: 3

## Classes

- `SkillSpec`
- `SkillsLoader`

## Functions

- `__init__`
- `_atomic_write_state`
- `_build_execution_contract`
- `_bundled_allowlist`
- `_bundled_skill_allowed`
- `_coerce_env_names`
- `_coerce_list`
- `_config_value_present`
- `_default_state_payload`
- `_ensure_discovery_cache`
- `_entry_state`
- `_escape_xml`
- `_extract_frontmatter`
- `_extract_frontmatter_block`
- `_extract_frontmatter_legacy`
- `_extract_requirement_map`
- `_extract_runtime_metadata`
- `_extract_skill_entries`
- `_flush_and_fsync`
- `_is_preferred_candidate`
- `_load_state_payload`
- `_load_watchfiles_awatch`
- `_missing_requirements`
- `_normalize_os_name`
- `_parse_header`
- `_parse_inline_value`
- `_rebuild_discovery_cache`
- `_refresh_runtime_status`
- `_resolve_active_config_payload`
- `_resolve_skill_entry_api_key`
- `_resolved_home`
- `_roots_signature`
- `_runtime_requirements_for_spec`
- `_serialize_frontmatter_value`
- `_skill_entry_enabled`
- `_skill_entry_env_overrides`
- `_skill_entry_payload`
- `_source_label`
- `_to_bool`
- `_watch_targets`
- `_watcher_apply_report`
- `_watcher_done_callback`
- `_watcher_record_failure`
- `_watcher_tick`
- `always_on`
- `build_skills_summary`
- `clear_version_pin`
- `diagnostics_report`
- `discover`
- `flush`
- `get`
- `invalidate`
- `load_skill_content`
- `load_skill_full`
- `load_skills_for_context`
- `refresh`
- `render_for_prompt`
- `resolved_env_overrides`
- `set_enabled`
- `set_pinned`
- `set_version_pin`
- `watcher_status`
- `_loop` (async)
- `_watcher_loop_poll` (async)
- `_watcher_loop_watchfiles` (async)
- `_watcher_refresh_once` (async)
- `start_watcher` (async)
- `stop_watcher` (async)

## Constants

- `_ACTIVE_CONFIG_CACHE`
- `_ENV_NAME_RE`
- `_KEY_VALUE_RE`
- `_SOURCE_PRIORITY`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/skills.py`.
- Cross-reference `CONNECTIONS_skills.md` to see how this file fits into the wider system.
