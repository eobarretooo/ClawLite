from __future__ import annotations

import re

_BRACKETED_SYSTEM_TAG_RE = re.compile(r"\[\s*(System\s*Message|System|Assistant|Internal)\s*\]", re.IGNORECASE)
_LINE_SYSTEM_PREFIX_RE = re.compile(r"^(\s*)System:(?=\s|$)", re.IGNORECASE | re.MULTILINE)


def normalize_inbound_text_newlines(input_text: str) -> str:
    """Normalize actual newline characters without touching literal escape sequences."""
    return str(input_text or "").replace("\r\n", "\n").replace("\r", "\n")


def sanitize_inbound_system_tags(input_text: str) -> str:
    """Neutralize user-controlled strings that spoof internal system markers."""
    normalized = normalize_inbound_text_newlines(input_text)
    return _LINE_SYSTEM_PREFIX_RE.sub(
        r"\1System (untrusted):",
        _BRACKETED_SYSTEM_TAG_RE.sub(lambda match: f"({match.group(1)})", normalized),
    )


__all__ = [
    "normalize_inbound_text_newlines",
    "sanitize_inbound_system_tags",
]
