# READ clawlite/tools/exec.py

## Identity

- Path: `clawlite/tools/exec.py`
- Area: `tools`
- Extension: `.py`
- Lines: 1029
- Size bytes: 42941
- SHA1: `1946c8aa5015699007f169475f97d4de8067c41f`

## Summary

`clawlite.tools.exec` is a Python module in the `tools` area. It defines 1 class(es), led by `ExecTool`. It exposes 37 function(s), including `__init__`, `_bash_compatible_path`, `_binary_name`, `health_check`, `run`. It depends on 14 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 35
- Async functions: 2
- Constants: 27
- Internal imports: 3
- Imported by: 5
- Matching tests: 3

## Classes

- `ExecTool`

## Functions

- `__init__`
- `_bash_compatible_path`
- `_binary_name`
- `_clamp_max_output_chars`
- `_extract_absolute_paths`
- `_extract_explicit_shell_command`
- `_guard_command`
- `_guard_env_split_string_payloads`
- `_guard_explicit_shell_command`
- `_guard_inline_runtime_fetch_targets`
- `_guard_network_fetch_targets`
- `_guard_python_module_fetch_targets`
- `_inline_runtime_payload`
- `_is_blocked_ip`
- `_is_env_assignment`
- `_is_windows_absolute_path`
- `_iter_network_fetch_segments`
- `_iter_network_fetch_target_urls`
- `_match_any`
- `_needs_shell_wrapper`
- `_network_fetch_binary_name`
- `_normalize_env_overrides`
- `_normalize_windows_command`
- `_path_like_tokens`
- `_resolve_cwd`
- `_resolve_inline_runtime_start`
- `_resolve_shell_like_path`
- `_resolve_windows_path_command`
- `_runtime_family`
- `_shell_like_paths`
- `_transparent_runtime_wrapper_flag_consumption`
- `_transparent_runtime_wrapper_name`
- `_truncate_output`
- `_validate_network_fetch_url`
- `args_schema`
- `health_check` (async)
- `run` (async)

## Constants

- `DEFAULT_MAX_OUTPUT_CHARS`
- `MAX_MAX_OUTPUT_CHARS`
- `MIN_MAX_OUTPUT_CHARS`
- `_BLOCKED_ENV_OVERRIDE_EXACT`
- `_BLOCKED_ENV_OVERRIDE_PREFIXES`
- `_CURL_SKIP_VALUE_FLAGS`
- `_CURL_URL_FLAGS`
- `_ENV_ASSIGNMENT_RE`
- `_ENV_NAME_RE`
- `_HTTP_URL_RE`
- `_INLINE_RUNTIME_FLAGS`
- `_INLINE_RUNTIME_NETWORK_HINTS`
- `_NETWORK_FETCH_BINARIES`
- `_POSIX_SHELL_BINARIES`
- `_POSIX_SHELL_COMMAND_FLAGS`
- `_POWERSHELL_SKIP_VALUE_FLAGS`
- `_POWERSHELL_URL_FLAGS`
- `_PYTHON_NETWORK_MODULES`
- `_SHELL_CONTROL_TOKENS`
- `_SHELL_META_RE`
- `_SHELL_PATH_RE`
- `_TIMEOUT_DURATION_RE`
- `_TRANSPARENT_RUNTIME_WRAPPERS`
- `_TRANSPARENT_RUNTIME_WRAPPER_FLAGS`
- `_WINDOWS_CMD_BUILTINS`
- `_WINDOWS_SHELL_BINARIES`
- `_WINDOWS_SHELL_COMMAND_FLAGS`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/exec.py`.
- Cross-reference `CONNECTIONS_exec.md` to see how this file fits into the wider system.
