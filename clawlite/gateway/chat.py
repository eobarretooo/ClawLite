from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from clawlite.config import settings as app_settings
from clawlite.config.settings import load_config
from clawlite.gateway.utils import (
    _append_jsonl,
    _estimate_cost_parts_usd,
    _estimate_tokens,
    _iso_now,
    _load_dashboard_settings,
    _log,
    _read_jsonl,
)


def _dashboard_dir() -> Path:
    return Path(app_settings.CONFIG_DIR) / "dashboard"


def _sessions_file() -> Path:
    return _dashboard_dir() / "sessions.jsonl"


def _telemetry_file() -> Path:
    return _dashboard_dir() / "telemetry.jsonl"


def _normalize_chat_meta(meta: dict[str, Any] | None, requested_model: str) -> dict[str, Any]:
    row = dict(meta or {})
    row["model"] = str(row.get("model") or requested_model)
    row["mode"] = str(row.get("mode") or "unknown")
    row["reason"] = str(row.get("reason") or "unknown")
    return row


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


async def _run_agent_reply(session_id: str, text: str, hooks: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    prompt = _build_chat_prompt(text, hooks)

    from clawlite.core.agent import run_task_with_meta

    try:
        output, meta = await asyncio.to_thread(run_task_with_meta, prompt, "", session_id)
    except TypeError:
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
    telem_path = _telemetry_file()
    telem_path.parent.mkdir(parents=True, exist_ok=True)
    _append_jsonl(telem_path, row)
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

    sessions_path = _sessions_file()
    sessions_path.parent.mkdir(parents=True, exist_ok=True)

    user_msg = {"ts": _iso_now(), "session_id": session_id, "role": "user", "text": clean_text}
    _append_jsonl(sessions_path, user_msg)

    reply, meta = await _run_agent_reply(session_id, clean_text, hooks)
    meta = _normalize_chat_meta(meta, requested_model)

    assistant_msg = {"ts": _iso_now(), "session_id": session_id, "role": "assistant", "text": reply}
    _append_jsonl(sessions_path, assistant_msg)

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


async def _stream_chat_message(session_id: str, text: str):  # -> AsyncGenerator[dict[str, Any], None]
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Mensagem vazia")

    cfg = load_config()
    settings = _load_dashboard_settings()
    requested_model = str(cfg.get("model", "openai/gpt-4o-mini"))
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}

    sessions_path = _sessions_file()
    sessions_path.parent.mkdir(parents=True, exist_ok=True)

    user_msg = {"ts": _iso_now(), "session_id": session_id, "role": "user", "text": clean_text}
    _append_jsonl(sessions_path, user_msg)

    prompt = _build_chat_prompt(clean_text, hooks)

    loop = asyncio.get_running_loop()
    q = asyncio.Queue()

    from clawlite.core.agent import run_task_stream_with_meta

    def _worker():
        try:
            try:
                out_stream, meta = run_task_stream_with_meta(prompt, "", session_id)
            except TypeError:
                out_stream, meta = run_task_stream_with_meta(prompt)
            asyncio.run_coroutine_threadsafe(q.put(("meta", meta)), loop)
            for chunk in out_stream:
                asyncio.run_coroutine_threadsafe(q.put(("chunk", chunk)), loop)
            asyncio.run_coroutine_threadsafe(q.put(("done", None)), loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(q.put(("error", str(e))), loop)

    import threading

    threading.Thread(target=_worker, daemon=True).start()

    meta = None
    full_reply: list[str] = []

    while True:
        msg_type, data = await q.get()
        if msg_type == "meta":
            meta = _normalize_chat_meta(data if isinstance(data, dict) else {}, requested_model)
            yield {"type": "meta", "data": meta}
        elif msg_type == "chunk":
            full_reply.append(data)
            yield {"type": "chunk", "data": data}
        elif msg_type == "error":
            yield {"type": "error", "data": data}
            return
        elif msg_type == "done":
            break

    reply = "".join(full_reply)
    reply = _build_chat_reply(reply, hooks)

    assistant_msg = {"ts": _iso_now(), "session_id": session_id, "role": "assistant", "text": reply}
    _append_jsonl(sessions_path, assistant_msg)

    if not meta:
        meta = {"mode": "error", "reason": "stream_failed", "model": requested_model}
    meta = _normalize_chat_meta(meta, requested_model)

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
        "chat.message.stream",
        level="error" if str(meta.get("mode")) == "error" else "info",
        data={
            "session_id": session_id,
            "tokens": telemetry_row["tokens"],
            "cost_usd": telemetry_row["cost_usd"],
            "mode": telemetry_row["mode"],
            "model": effective_model,
        },
    )
    yield {
        "type": "done",
        "assistant_message": assistant_msg,
        "telemetry": telemetry_row,
        "meta": meta,
    }


def _collect_session_index(query: str = "") -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(_sessions_file()):
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
    return [r for r in _read_jsonl(_sessions_file()) if str(r.get("session_id", "")) == session_id]
