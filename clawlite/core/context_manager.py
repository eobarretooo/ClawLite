"""
ClawLite Context Manager — Token counting e auto-compactação.

Gerencia a janela de contexto para evitar overflow e manter
conversas longas funcionais com resumo automático de turnos antigos.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from clawlite.core.model_catalog import estimate_tokens, context_window, get_model_or_default

logger = logging.getLogger(__name__)

# Reservas de tokens
HARD_MIN_RESERVE = 2_000       # Mínimo absoluto para resposta
WARN_THRESHOLD = 20_000        # Avisa quando sobra menos que isso
COMPACTION_TRIGGER = 0.85      # Compacta quando uso > 85% do context window


@dataclass
class ContextBudget:
    """Estado do orçamento de contexto."""
    model: str
    window_size: int
    used_tokens: int
    available_tokens: int
    usage_ratio: float
    needs_compaction: bool
    warning: str = ""


@dataclass
class CompactedHistory:
    """Resultado da compactação de histórico."""
    messages: list[dict[str, Any]]
    summary: str
    original_count: int
    compacted_count: int
    tokens_saved: int


def evaluate_context_budget(
    model_key: str,
    prompt_text: str,
    history_text: str = "",
) -> ContextBudget:
    """Avalia o orçamento de contexto para uma chamada."""
    window = context_window(model_key)
    entry = get_model_or_default(model_key)

    prompt_tokens = estimate_tokens(prompt_text)
    history_tokens = estimate_tokens(history_text)
    used = prompt_tokens + history_tokens
    available = max(0, window - used - HARD_MIN_RESERVE)
    ratio = used / window if window > 0 else 1.0

    warning = ""
    needs_compaction = False

    if available < HARD_MIN_RESERVE:
        warning = f"CRITICO: Apenas {available} tokens livres. Compactação urgente."
        needs_compaction = True
    elif ratio >= COMPACTION_TRIGGER:
        warning = f"AVISO: {ratio:.0%} do context window usado. Compactação recomendada."
        needs_compaction = True
    elif available < WARN_THRESHOLD:
        warning = f"ATENÇÃO: {available} tokens restantes de {window}."

    return ContextBudget(
        model=model_key,
        window_size=window,
        used_tokens=used,
        available_tokens=available,
        usage_ratio=ratio,
        needs_compaction=needs_compaction,
        warning=warning,
    )


def compact_history(
    messages: list[dict[str, Any]],
    model_key: str,
    keep_recent: int = 4,
) -> CompactedHistory:
    """
    Compacta histórico de mensagens mantendo as mais recentes
    e resumindo as antigas em um bloco de contexto.
    """
    if len(messages) <= keep_recent:
        return CompactedHistory(
            messages=messages,
            summary="",
            original_count=len(messages),
            compacted_count=len(messages),
            tokens_saved=0,
        )

    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Gera resumo das mensagens antigas
    old_texts = []
    for m in old_messages:
        role = m.get("role", "info")
        text = (m.get("text") or "").strip()
        if text:
            old_texts.append(f"{role}: {text[:200]}")

    old_content = "\n".join(old_texts)
    old_tokens = estimate_tokens(old_content)

    # Resumo compactado (1/4 do tamanho original)
    summary_lines = []
    for m in old_messages:
        role = m.get("role", "info")
        text = (m.get("text") or "").strip()
        if text and role in ("user", "assistant"):
            summary_lines.append(f"- {role}: {text[:80]}")

    # Limita o resumo
    summary = "\n".join(summary_lines[:10])
    if len(summary_lines) > 10:
        summary += f"\n... (+{len(summary_lines) - 10} mensagens anteriores)"

    summary_tokens = estimate_tokens(summary)
    tokens_saved = max(0, old_tokens - summary_tokens)

    # Insere resumo como primeira mensagem
    summary_msg = {
        "role": "system",
        "text": f"[Resumo do histórico anterior]\n{summary}",
    }

    compacted = [summary_msg] + recent_messages

    logger.info(
        "Compacted history: %d -> %d messages, saved ~%d tokens",
        len(messages), len(compacted), tokens_saved,
    )

    return CompactedHistory(
        messages=compacted,
        summary=summary,
        original_count=len(messages),
        compacted_count=len(compacted),
        tokens_saved=tokens_saved,
    )


def build_context_with_budget(
    prompt: str,
    system_prompt: str,
    history_messages: list[dict[str, Any]],
    model_key: str,
    memory_snippets: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """
    Constrói o contexto completo respeitando o orçamento de tokens.
    Compacta automaticamente se necessário.
    """
    # Monta texto do histórico para avaliação
    history_text = ""
    for m in history_messages:
        text = (m.get("text") or "").strip()
        if text:
            history_text += text + "\n"

    full_prompt = f"{system_prompt}\n{memory_snippets}\n{prompt}"
    budget = evaluate_context_budget(model_key, full_prompt, history_text)

    if budget.warning:
        logger.warning(budget.warning)

    final_messages = history_messages

    if budget.needs_compaction:
        result = compact_history(history_messages, model_key)
        final_messages = result.messages
        if result.tokens_saved > 0:
            logger.info("Auto-compaction saved ~%d tokens", result.tokens_saved)

    return full_prompt, final_messages
