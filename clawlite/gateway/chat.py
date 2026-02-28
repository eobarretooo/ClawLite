from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException

from clawlite.config.settings import load_config
from clawlite.core.agent import run_task_with_meta
from clawlite.gateway.state import SESSIONS_FILE, TELEMETRY_FILE
from clawlite.gateway.utils import (
    _append_jsonl,
    _estimate_cost_parts_usd,
    _estimate_tokens,
    _iso_now,
    _load_dashboard_settings,
    _log,
    _read_jsonl,
)


def _build_chat_prompt(text: str, hooks: dict[str, Any]) -> str:
    pre = str(hooks.get("pre", "")).strip()
    if pre:
        return f"{pre}\n\n{text}"
    return text


def _build_chat_reply(raw_output: str, hooks: dict[str, Any]) -> str:
    post = str(hooks.get("post", "")).strip()
    if not post:
        return raw_output
    return f"{raw_output}\n\n{post}"


async def _run_agent_reply(text: str, hooks: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    prompt = _build_chat_prompt(text, hooks)
    output, meta = await asyncio.to_thread(run_task_with_meta, prompt)
    return _build_chat_reply(output, hooks), meta


def _record_telemetry(
    *,
    session_id: str,
    text: str,
    reply: str,
    requested_model: str,
    effective_model: str,
    mode: str,
    reason: str,
) -> dict[str, Any]:
    prompt_tokens = _estimate_tokens(text)
    completion_tokens = _estimate_tokens(reply)
    tokens = prompt_tokens + completion_tokens
    prompt_cost_usd, completion_cost_usd = _estimate_cost_parts_usd(prompt_tokens, completion_tokens, effective_model)
    cost_usd = round(prompt_cost_usd + completion_cost_usd, 6)
    row = {
        "ts": _iso_now(),
        "session_id": session_id,
        "model_requested": requested_model,
        "model_effective": effective_model,
        "mode": mode,
        "reason": reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens": tokens,
        "prompt_cost_usd": prompt_cost_usd,
        "completion_cost_usd": completion_cost_usd,
        "cost_usd": cost_usd,
    }
    _append_jsonl(TELEMETRY_FILE, row)
    return row


async def _handle_chat_message(session_id: str, text: str) -> dict[str, Any]:
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Mensagem vazia")

    cfg = load_config()
    settings = _load_dashboard_settings()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}

    user_msg = {"ts": _iso_now(), "session_id": session_id, "role": "user", "text": clean_text}
    _append_jsonl(SESSIONS_FILE, user_msg)

    reply, meta = await _run_agent_reply(clean_text, hooks)
    assistant_msg = {"ts": _iso_now(), "session_id": session_id, "role": "assistant", "text": reply}
    _append_jsonl(SESSIONS_FILE, assistant_msg)

    effective_model = str(meta.get("model") or requested_model)
    telemetry_row = _record_telemetry(
        session_id=session_id,
        text=clean_text,
        reply=reply,
        requested_model=requested_model,
        effective_model=effective_model,
        mode=str(meta.get("mode", "unknown")),
        reason=str(meta.get("reason", "unknown")),
    )
    _log(
        "chat.message",
        level="error" if str(meta.get("mode")) == "error" else "info",
        data={
            "session_id": session_id,
            "tokens": telemetry_row["tokens"],
            "cost_usd": telemetry_row["cost_usd"],
            "mode": telemetry_row["mode"],
            "model": effective_model,
        },
    )
    return {
        "assistant_message": assistant_msg,
        "telemetry": telemetry_row,
        "meta": meta,
    }


def _collect_session_index(query: str = "") -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(SESSIONS_FILE):
        sid = str(row.get("session_id", "")).strip()
        if not sid:
            continue
        item = grouped.setdefault(
            sid,
            {
                "session_id": sid,
                "messages": 0,
                "last_ts": "",
                "preview": "",
            },
        )
        item["messages"] += 1
        ts = str(row.get("ts", ""))
        if ts >= item["last_ts"]:
            item["last_ts"] = ts
            text = str(row.get("text", "")).strip()
            if text:
                item["preview"] = text[:140]

    items = sorted(grouped.values(), key=lambda i: i.get("last_ts", ""), reverse=True)
    if query:
        q = query.lower()
        items = [i for i in items if q in i.get("session_id", "").lower() or q in i.get("preview", "").lower()]
    return items


def _session_messages(session_id: str) -> list[dict[str, Any]]:
    return [r for r in _read_jsonl(SESSIONS_FILE) if str(r.get("session_id", "")) == session_id]
