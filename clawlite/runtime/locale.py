from __future__ import annotations

import locale
import os


SUPPORTED_LANGS = {"pt-br", "en"}


def detect_language(default: str = "pt-br") -> str:
    env = (os.getenv("CLAWLITE_LANG") or os.getenv("LANG") or "").lower()

    try:
        loc = (locale.getlocale()[0] or "").lower()
    except Exception:
        loc = ""

    joined = f"{env} {loc}"
    if "pt_br" in joined or "pt-br" in joined or joined.startswith("pt"):
        return "pt-br"
    if joined.startswith("en") or " en_" in joined or " en-" in joined:
        return "en"
    return default if default in SUPPORTED_LANGS else "pt-br"
