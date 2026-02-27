"""Preference Learning - detecta e persiste preferências do usuário."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PREFS_PATH = Path.home() / ".clawlite" / "preferences.json"

# Padrões comuns de correção
_CORRECTION_PATTERNS = [
    (r"(?:seja|ser|fique|ficar)\s+mais\s+(curt[oa]|brev[e]|concis[oa])", "resposta_curta"),
    (r"(?:use|usar|em)\s+(?:pt-?br|português)", "idioma_ptbr"),
    (r"(?:não|nunca)\s+(?:faça|faz|use|usar)\s+(.+)", "evitar"),
    (r"(?:sempre|preferir?)\s+(.+)", "preferir"),
    (r"(?:mais|menos)\s+(formal|informal|técnic[oa]|simples)", "tom"),
    (r"(?:formato|formatar?)\s+(?:em|como)\s+(json|markdown|texto|tabela|lista)", "formato"),
]


def _load_prefs() -> list[dict[str, Any]]:
    if PREFS_PATH.exists():
        try:
            return json.loads(PREFS_PATH.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_prefs(prefs: list[dict[str, Any]]) -> None:
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREFS_PATH.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), "utf-8")


def learn_preference(context: str, correction: str) -> dict[str, Any] | None:
    """Detecta e registra uma preferência a partir de uma correção do usuário."""
    pref: dict[str, Any] | None = None

    for pattern, category in _CORRECTION_PATTERNS:
        m = re.search(pattern, correction, re.IGNORECASE)
        if m:
            pref = {
                "category": category,
                "value": m.group(1) if m.lastindex else correction,
                "raw_correction": correction[:200],
                "context_snippet": context[:200],
                "learned_at": datetime.now(timezone.utc).isoformat(),
            }
            break

    if pref is None:
        # Fallback genérico
        pref = {
            "category": "geral",
            "value": correction[:200],
            "raw_correction": correction[:200],
            "context_snippet": context[:200],
            "learned_at": datetime.now(timezone.utc).isoformat(),
        }

    prefs = _load_prefs()
    # Evitar duplicatas exatas
    if not any(p["category"] == pref["category"] and p["value"] == pref["value"] for p in prefs):
        prefs.append(pref)
        # Máximo 50 preferências
        prefs = prefs[-50:]
        _save_prefs(prefs)
        return pref
    return None


def get_preferences() -> list[dict[str, Any]]:
    """Retorna todas as preferências aprendidas."""
    return _load_prefs()


def build_preference_prefix() -> str:
    """Gera um prefixo de system prompt baseado nas preferências aprendidas."""
    prefs = _load_prefs()
    if not prefs:
        return ""

    lines = ["[Preferências do usuário aprendidas automaticamente:]"]
    for p in prefs:
        cat = p.get("category", "geral")
        val = p.get("value", "")
        if cat == "resposta_curta":
            lines.append("- Prefere respostas curtas e concisas")
        elif cat == "idioma_ptbr":
            lines.append("- Usar português brasileiro (PT-BR)")
        elif cat == "evitar":
            lines.append(f"- Evitar: {val}")
        elif cat == "preferir":
            lines.append(f"- Sempre: {val}")
        elif cat == "tom":
            lines.append(f"- Tom desejado: {val}")
        elif cat == "formato":
            lines.append(f"- Formato preferido: {val}")
        else:
            lines.append(f"- {val}")
    return "\n".join(lines)


def remove_preference(index: int) -> bool:
    """Remove uma preferência pelo índice."""
    prefs = _load_prefs()
    if 0 <= index < len(prefs):
        prefs.pop(index)
        _save_prefs(prefs)
        return True
    return False
