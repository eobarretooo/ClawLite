# READ clawlite/core/injection_guard.py

## Identity

- Path: `clawlite/core/injection_guard.py`
- Area: `core`
- Extension: `.py`
- Lines: 380
- Size bytes: 17198
- SHA1: `44c48b4e5d8a50851bb56ef096c346bb21690958`

## Summary

`clawlite.core.injection_guard` is a Python module in the `core` area. It defines 2 class(es), led by `ScanResult`, `ThreatLevel`. It exposes 10 function(s), including `_audit`, `_normalize_unicode`, `_scan_encoded_payloads`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 10
- Async functions: 0
- Constants: 11
- Internal imports: 2
- Imported by: 4
- Matching tests: 1

## Classes

- `ScanResult`
- `ThreatLevel`

## Functions

- `_audit`
- `_normalize_unicode`
- `_scan_encoded_payloads`
- `_strip_invisible`
- `injection_guard_section`
- `is_clean`
- `scan_inbound`
- `scan_output`
- `summary`
- `wrap_user_text`

## Constants

- `BLOCK`
- `CLEAN`
- `WARN`
- `_B64_MIN_LENGTH`
- `_B64_RE`
- `_CODE_PATTERNS`
- `_DECODED_INJECTION_RE`
- `_HEX_RE`
- `_INJECTION_PATTERNS`
- `_INVISIBLE_CHARS`
- `_OUTPUT_DANGER_PATTERNS`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/injection_guard.py`.
- Cross-reference `CONNECTIONS_injection_guard.md` to see how this file fits into the wider system.
