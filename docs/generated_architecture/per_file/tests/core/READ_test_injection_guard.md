# READ tests/core/test_injection_guard.py

## Identity

- Path: `tests/core/test_injection_guard.py`
- Area: `tests`
- Extension: `.py`
- Lines: 118
- Size bytes: 4434
- SHA1: `8a0baecba763a54eb96c638788c7475be944cfc5`

## Summary

`tests.core.test_injection_guard` is a Python module in the `tests` area. It exposes 16 function(s), including `test_base64_encoded_injection_blocked`, `test_blocked_sets_sanitized_text`, `test_clean_message_passes`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 16
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `test_base64_encoded_injection_blocked`
- `test_blocked_sets_sanitized_text`
- `test_clean_message_passes`
- `test_clean_output_passes`
- `test_injection_guard_section_nonempty`
- `test_invisible_chars_stripped_and_warned`
- `test_jailbreak_attempt_blocked`
- `test_original_text_preserved`
- `test_output_empty_string`
- `test_output_with_dangerous_shell_flagged`
- `test_sanitized_text_is_unicode_normalized`
- `test_shell_fork_bomb_blocked`
- `test_system_override_is_blocked`
- `test_wrap_user_text_adds_tags`
- `test_wrap_user_text_empty`
- `test_xss_script_tag_blocked`

## Notable String Markers

- `test_base64_encoded_injection_blocked`
- `test_blocked_sets_sanitized_text`
- `test_clean_message_passes`
- `test_clean_output_passes`
- `test_injection_guard_section_nonempty`
- `test_invisible_chars_stripped_and_warned`
- `test_jailbreak_attempt_blocked`
- `test_original_text_preserved`
- `test_output_empty_string`
- `test_output_with_dangerous_shell_flagged`
- `test_sanitized_text_is_unicode_normalized`
- `test_shell_fork_bomb_blocked`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_injection_guard.py`.
- Cross-reference `CONNECTIONS_test_injection_guard.md` to see how this file fits into the wider system.
