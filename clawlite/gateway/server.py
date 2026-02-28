from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import secrets
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

try:
    from rich.console import Console
except Exception:
    Console = None  # type: ignore

from clawlite.config.settings import CONFIG_DIR, load_config, save_config
from clawlite.core.agent import run_task_with_meta
from clawlite.mcp import add_server, install_template, list_servers, remove_server, search_marketplace
from clawlite.mcp_server import handle_mcp_jsonrpc
from clawlite.runtime.multiagent import bind_agent, create_agent, list_agent_bindings, list_agents
from clawlite.runtime.conversation_cron import add_cron_job, list_cron_jobs, remove_cron_job
from clawlite.skills.marketplace import (
    DEFAULT_DOWNLOAD_BASE_URL,
    SkillMarketplaceError,
    load_hub_manifest,
    publish_skill,
    update_skills,
)

app = FastAPI(title="ClawLite Gateway", version="0.3.0")
connections: set[WebSocket] = set()
chat_connections: set[WebSocket] = set()
log_connections: dict[WebSocket, dict[str, str]] = {}
STARTED_AT = datetime.now(timezone.utc)

LOG_RING: deque[dict[str, Any]] = deque(maxlen=500)

_LOGS_DIR = CONFIG_DIR / "logs"
_GATEWAY_LOG_FILE = _LOGS_DIR / "gateway.log"
_CONSOLE = Console() if Console else None


DASHBOARD_DIR = CONFIG_DIR / "dashboard"
SESSIONS_FILE = DASHBOARD_DIR / "sessions.jsonl"
TELEMETRY_FILE = DASHBOARD_DIR / "telemetry.jsonl"
SETTINGS_FILE = DASHBOARD_DIR / "settings.json"


def _version() -> str:
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("clawlite")
    except Exception:
        return "dev"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    if not slug:
        raise HTTPException(status_code=400, detail="Slug inválido")
    return slug


def _ensure_dashboard_store() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dashboard_store()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except json.JSONDecodeError:
            continue
    return rows


def _load_dashboard_settings() -> dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {
        "theme": "dark",
        "hooks": {"pre": "", "post": ""},
    }


def _save_dashboard_settings(data: dict[str, Any]) -> None:
    _ensure_dashboard_store()
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.strip()) // 4)


def _looks_cheap_model(model: str) -> bool:
    return any(x in model.lower() for x in ("mini", "flash", "haiku", "nano"))


def _pricing_per_1k(model: str) -> tuple[float, float]:
    normalized = model.lower()
    if normalized.startswith("openai/"):
        return (0.00015, 0.0006) if _looks_cheap_model(model) else (0.005, 0.015)
    if normalized.startswith("openrouter/"):
        return (0.0005, 0.0015) if _looks_cheap_model(model) else (0.004, 0.012)
    if normalized.startswith("ollama/") or normalized.startswith("local/"):
        return 0.0, 0.0
    return (0.0005, 0.0015) if _looks_cheap_model(model) else (0.003, 0.009)


def _estimate_cost_parts_usd(prompt_tokens: int, completion_tokens: int, model: str) -> tuple[float, float]:
    in_rate, out_rate = _pricing_per_1k(model)
    prompt_cost = round((prompt_tokens / 1000.0) * in_rate, 6)
    completion_cost = round((completion_tokens / 1000.0) * out_rate, 6)
    return prompt_cost, completion_cost


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _period_start(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    p = period.strip().lower()
    if p in {"", "all"}:
        return None
    if p == "24h":
        return now - timedelta(hours=24)
    if p == "7d":
        return now - timedelta(days=7)
    if p == "30d":
        return now - timedelta(days=30)
    if p == "today":
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if p == "week":
        base = now - timedelta(days=now.weekday())
        return datetime(base.year, base.month, base.day, tzinfo=timezone.utc)
    if p == "month":
        return datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return None


def _telemetry_tokens(row: dict[str, Any]) -> tuple[int, int, int]:
    prompt = int(row.get("prompt_tokens", 0) or 0)
    completion = int(row.get("completion_tokens", 0) or 0)
    total = int(row.get("tokens", 0) or 0)
    if prompt == 0 and completion == 0 and total > 0:
        prompt = total // 2
        completion = total - prompt
    if total == 0:
        total = prompt + completion
    return prompt, completion, total


def _telemetry_costs(row: dict[str, Any]) -> tuple[float, float, float]:
    prompt_cost = float(row.get("prompt_cost_usd", 0.0) or 0.0)
    completion_cost = float(row.get("completion_cost_usd", 0.0) or 0.0)
    total_cost = float(row.get("cost_usd", 0.0) or 0.0)
    if prompt_cost == 0.0 and completion_cost == 0.0 and total_cost > 0.0:
        prompt_cost = round(total_cost / 2.0, 6)
        completion_cost = round(total_cost - prompt_cost, 6)
    if total_cost == 0.0:
        total_cost = round(prompt_cost + completion_cost, 6)
    return prompt_cost, completion_cost, total_cost


def _log_matches(entry: dict[str, Any], *, level: str = "", event: str = "", query: str = "") -> bool:
    if level and str(entry.get("level", "")).lower() != level.lower():
        return False
    if event and event.lower() not in str(entry.get("event", "")).lower():
        return False
    if query:
        haystack = json.dumps(entry, ensure_ascii=False).lower()
        if query.lower() not in haystack:
            return False
    return True


def _filter_logs(rows: list[dict[str, Any]], *, level: str = "", event: str = "", query: str = "") -> list[dict[str, Any]]:
    return [row for row in rows if _log_matches(row, level=level, event=event, query=query)]


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


def _format_log_line(entry: dict[str, Any]) -> tuple[str, str]:
    dt = _parse_ts(entry.get("ts")) or datetime.now(timezone.utc)
    ts = dt.strftime("%Y-%m-%d %H:%M:%S")
    level = str(entry.get("level", "info")).upper()
    event = str(entry.get("event", "system"))
    data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
    category = (event.split(".", 1)[0] if "." in event else event).lower()

    if event == "gateway.started":
        msg = f"gateway started on {data.get('host', '0.0.0.0')}:{data.get('port', '-') }"
        category = "gateway"
    elif event == "chat.message":
        msg = f"chat session={data.get('session_id','-')} model={data.get('model','-')} mode={data.get('mode','-')}"
        category = "chat"
    elif event.startswith("skills."):
        slug = data.get("slug", "-")
        verb = event.split(".", 1)[1] if "." in event else "action"
        msg = f"skill {slug}.{verb} → ok"
        category = "skill"
    else:
        suffix = ""
        if data:
            try:
                suffix = " " + json.dumps(data, ensure_ascii=False)
            except Exception:
                suffix = ""
        msg = f"{event}{suffix}"

    plain = f"[{ts}] {level} {category} {msg}".strip()

    color = "cyan"
    if level == "WARN":
        color = "yellow"
    elif level == "ERROR":
        color = "red"
    rich_line = f"[{ts}] [{color}]{level}[/{color}] [bold]{category}[/bold] {msg}"
    return plain, rich_line


def _persist_log_line(text: str) -> None:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with _GATEWAY_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def _log(event: str, level: str = "info", data: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "ts": _iso_now(),
        "level": level,
        "event": event,
        "data": data or {},
    }
    LOG_RING.append(entry)

    plain, rich_line = _format_log_line(entry)
    _persist_log_line(plain)
    if _CONSOLE is not None:
        _CONSOLE.print(rich_line)
    else:
        print(plain)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return entry
    for ws, filters in list(log_connections.items()):
        if not _log_matches(
            entry,
            level=str(filters.get("level", "")),
            event=str(filters.get("event", "")),
            query=str(filters.get("q", "")),
        ):
            continue
        try:
            loop.create_task(ws.send_json({"type": "log", "payload": entry}))
        except Exception:
            log_connections.pop(ws, None)
    return entry


def _token() -> str:
    cfg = load_config()
    t = os.getenv("CLAWLITE_GATEWAY_TOKEN") or cfg.get("gateway", {}).get("token", "")
    if not t:
        t = secrets.token_urlsafe(24)
        cfg.setdefault("gateway", {})["token"] = t
        save_config(cfg)
    return t


def _check_bearer(auth: str | None) -> None:
    expected = _token()
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    got = auth.removeprefix("Bearer ").strip()
    if got != expected:
        raise HTTPException(status_code=403, detail="Invalid token")


def _hub_manifest_path() -> Path:
    custom = os.getenv("CLAWLITE_HUB_MANIFEST")
    if custom:
        return Path(custom).expanduser()
    return Path.cwd() / "hub" / "marketplace" / "manifest.local.json"


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


def _skills_dir() -> Path:
    return Path.cwd() / "skills"


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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "ok": True,
        "service": "clawlite-gateway",
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "connections": len(connections) + len(chat_connections) + len(log_connections),
    }


@app.get("/")
def root() -> HTMLResponse:
    html = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/dashboard")
def dashboard() -> HTMLResponse:
    html = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/api/dashboard/auth")
def api_dashboard_auth(payload: dict[str, Any]) -> JSONResponse:
    token = str(payload.get("token", "")).strip()
    ok = secrets.compare_digest(token, _token())
    return JSONResponse({"ok": ok})


@app.get("/api/status")
def api_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    return JSONResponse({
        "ok": True,
        "gateway": cfg.get("gateway", {}),
        "skills": cfg.get("skills", []),
        "connections": len(connections) + len(chat_connections) + len(log_connections),
    })


@app.post("/mcp")
def mcp_rpc(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse(handle_mcp_jsonrpc(payload))


@app.get("/api/mcp/list")
def api_mcp_list(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    rows = list_servers()
    return JSONResponse({"ok": True, "servers": rows})


@app.get("/api/mcp/config")
def api_mcp_config(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    rows = list_servers()
    return JSONResponse({"ok": True, "servers": rows})


@app.post("/api/mcp/add")
def api_mcp_add(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        row = add_server(str(payload.get("name", "")), str(payload.get("url", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "server": row})


@app.post("/api/mcp/remove")
def api_mcp_remove(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        removed = remove_server(str(payload.get("name", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Servidor MCP não encontrado")
    return JSONResponse({"ok": True, "removed": True})


@app.get("/api/mcp/search")
def api_mcp_search(q: str = Query(default=""), authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "items": search_marketplace(q)})


@app.post("/api/mcp/install")
def api_mcp_install(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    name = str(payload.get("name", "")).strip()
    try:
        row = install_template(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "server": row})


@app.get("/api/mcp/status")
def api_mcp_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    rows = list_servers()
    return JSONResponse(
        {
            "ok": True,
            "count": len(rows),
            "servers": [
                {
                    **row,
                    "status": "configured",
                    "connected": False,
                }
                for row in rows
            ],
        }
    )


@app.get("/api/dashboard/bootstrap")
def api_dashboard_bootstrap(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    settings = _load_dashboard_settings()
    return JSONResponse({
        "ok": True,
        "status": {
            "online": True,
            "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
            "model": cfg.get("model", "unknown"),
            "connections": len(connections) + len(chat_connections) + len(log_connections),
        },
        "settings": {
            "model": cfg.get("model", "openai/gpt-4o-mini"),
            "channels": cfg.get("channels", {}),
            "hooks": settings.get("hooks", {"pre": "", "post": ""}),
            "theme": settings.get("theme", "dark"),
        },
    })


@app.get("/api/dashboard/settings")
def api_dashboard_get_settings(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    settings = _load_dashboard_settings()
    return JSONResponse({
        "ok": True,
        "settings": {
            "model": cfg.get("model", "openai/gpt-4o-mini"),
            "channels": cfg.get("channels", {}),
            "hooks": settings.get("hooks", {"pre": "", "post": ""}),
            "theme": settings.get("theme", "dark"),
        },
    })


@app.put("/api/dashboard/settings")
def api_dashboard_save_settings(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    model = str(payload.get("model", cfg.get("model", ""))).strip() or cfg.get("model", "openai/gpt-4o-mini")
    channels = payload.get("channels", cfg.get("channels", {}))
    hooks = payload.get("hooks", _load_dashboard_settings().get("hooks", {"pre": "", "post": ""}))
    theme = str(payload.get("theme", "dark") or "dark")

    cfg["model"] = model
    if isinstance(channels, dict):
        cfg["channels"] = channels
    save_config(cfg)

    dashboard_settings = _load_dashboard_settings()
    dashboard_settings["hooks"] = hooks if isinstance(hooks, dict) else {"pre": "", "post": ""}
    dashboard_settings["theme"] = theme
    _save_dashboard_settings(dashboard_settings)

    _log("settings.updated", data={"model": model})
    return JSONResponse({"ok": True, "settings": {"model": model, "channels": cfg.get("channels", {}), "hooks": dashboard_settings["hooks"], "theme": theme}})


@app.get("/api/dashboard/status")
def api_dashboard_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    return JSONResponse({
        "ok": True,
        "online": True,
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "model": cfg.get("model", "unknown"),
        "connections": len(connections) + len(chat_connections) + len(log_connections),
    })


@app.get("/api/agents")
def api_agents(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "agents": [a.__dict__ for a in list_agents()], "bindings": list_agent_bindings()})


@app.post("/api/agents")
def api_agents_create(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        agent_id = create_agent(
            str(payload.get("name", "")),
            channel=str(payload.get("channel", "telegram")),
            role=str(payload.get("role", "")),
            personality=str(payload.get("personality", "")),
            credentials=str(payload.get("token", "")),
            account=str(payload.get("account", "")),
            orchestrator=bool(payload.get("orchestrator", False)),
            tags=[str(t) for t in (payload.get("tags") or [])],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "id": agent_id})


@app.post("/api/agents/bind")
def api_agents_bind(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        agent_id = bind_agent(str(payload.get("agent", "")), channel=str(payload.get("channel", "")), account=str(payload.get("account", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "agent_id": agent_id})


@app.get("/api/dashboard/skills")
def api_dashboard_skills(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    enabled = set(cfg.get("skills", []))
    local = []
    skills_dir = _skills_dir()
    if skills_dir.exists():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir():
                local.append(d.name)
    return JSONResponse({
        "ok": True,
        "skills": [{"slug": slug, "enabled": slug in enabled} for slug in sorted(set(local) | enabled)],
    })


@app.post("/api/dashboard/skills/install")
def api_dashboard_skills_install(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    skills_dir = _skills_dir()
    skill_dir = skills_dir / slug
    created = not skill_dir.exists()
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        skill_file.write_text(f"# {slug}\n\nSkill local instalada via dashboard.\n", encoding="utf-8")

    cfg = load_config()
    active = set(cfg.get("skills", []))
    active.add(slug)
    cfg["skills"] = sorted(active)
    save_config(cfg)
    _log("skills.installed", data={"slug": slug, "created": created})
    return JSONResponse({"ok": True, "slug": slug, "created": created})


@app.post("/api/dashboard/skills/enable")
def api_dashboard_skills_enable(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    if not (_skills_dir() / slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' não encontrada no diretório local")
    cfg = load_config()
    active = set(cfg.get("skills", []))
    active.add(slug)
    cfg["skills"] = sorted(active)
    save_config(cfg)
    _log("skills.enabled", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug, "enabled": True})


@app.post("/api/dashboard/skills/disable")
def api_dashboard_skills_disable(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    cfg = load_config()
    if slug not in cfg.get("skills", []):
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' já está desativada ou não existe")
    cfg["skills"] = [s for s in cfg.get("skills", []) if s != slug]
    save_config(cfg)
    _log("skills.disabled", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug, "enabled": False})


@app.post("/api/dashboard/skills/remove")
def api_dashboard_skills_remove(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    skill_dir = _skills_dir() / slug
    cfg = load_config()
    was_enabled = slug in cfg.get("skills", [])
    if not skill_dir.exists() and not was_enabled:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' não encontrada")

    cfg["skills"] = [s for s in cfg.get("skills", []) if s != slug]
    save_config(cfg)

    if skill_dir.exists() and skill_dir.is_dir():
        for p in sorted(skill_dir.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                try:
                    p.rmdir()
                except OSError:
                    pass
        try:
            skill_dir.rmdir()
        except OSError:
            pass

    _log("skills.removed", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug, "removed": True})


@app.get("/api/dashboard/sessions")
def api_dashboard_sessions(
    authorization: str | None = Header(default=None),
    q: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "sessions": _collect_session_index(q)})


@app.get("/api/dashboard/sessions/{session_id}")
def api_dashboard_session_messages(session_id: str, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "session_id": session_id, "messages": _session_messages(session_id)})


@app.get("/api/dashboard/telemetry")
def api_dashboard_telemetry(
    authorization: str | None = Header(default=None),
    session_id: str = Query(default=""),
    period: str = Query(default="7d"),
    granularity: str = Query(default="auto"),
    start: str = Query(default=""),
    end: str = Query(default=""),
    limit: int = Query(default=200),
) -> JSONResponse:
    _check_bearer(authorization)
    rows = _read_jsonl(TELEMETRY_FILE)
    clean_session = session_id.strip()
    start_dt = _parse_ts(start) if start else _period_start(period)
    end_dt = _parse_ts(end) if end else None
    if start_dt and end_dt and end_dt < start_dt:
        raise HTTPException(status_code=400, detail="Intervalo inválido: end < start")

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if clean_session and str(row.get("session_id", "")) != clean_session:
            continue
        row_ts = _parse_ts(row.get("ts"))
        if start_dt and (row_ts is None or row_ts < start_dt):
            continue
        if end_dt and (row_ts is None or row_ts > end_dt):
            continue
        filtered.append(row)

    summary = {
        "events": 0,
        "sessions": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "tokens": 0,
        "prompt_cost_usd": 0.0,
        "completion_cost_usd": 0.0,
        "cost_usd": 0.0,
    }
    session_map: dict[str, dict[str, Any]] = {}

    use_hour = False
    if granularity.lower() == "hour":
        use_hour = True
    elif granularity.lower() == "auto":
        use_hour = period.lower() in {"24h", "today"}

    timeline_map: dict[str, dict[str, Any]] = {}
    for row in filtered:
        prompt_tokens, completion_tokens, tokens = _telemetry_tokens(row)
        prompt_cost, completion_cost, total_cost = _telemetry_costs(row)
        sid = str(row.get("session_id", "")).strip() or "unknown"

        summary["events"] += 1
        summary["prompt_tokens"] += prompt_tokens
        summary["completion_tokens"] += completion_tokens
        summary["tokens"] += tokens
        summary["prompt_cost_usd"] = round(summary["prompt_cost_usd"] + prompt_cost, 6)
        summary["completion_cost_usd"] = round(summary["completion_cost_usd"] + completion_cost, 6)
        summary["cost_usd"] = round(summary["cost_usd"] + total_cost, 6)

        item = session_map.setdefault(
            sid,
            {
                "session_id": sid,
                "events": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "tokens": 0,
                "cost_usd": 0.0,
                "last_ts": "",
            },
        )
        item["events"] += 1
        item["prompt_tokens"] += prompt_tokens
        item["completion_tokens"] += completion_tokens
        item["tokens"] += tokens
        item["cost_usd"] = round(item["cost_usd"] + total_cost, 6)
        ts = str(row.get("ts", ""))
        if ts >= item["last_ts"]:
            item["last_ts"] = ts

        dt = _parse_ts(row.get("ts"))
        if dt is None:
            continue
        if use_hour:
            bucket_dt = dt.replace(minute=0, second=0, microsecond=0)
            bucket = bucket_dt.isoformat().replace("+00:00", "Z")
        else:
            bucket = dt.strftime("%Y-%m-%d")
        bucket_item = timeline_map.setdefault(
            bucket,
            {
                "bucket": bucket,
                "events": 0,
                "tokens": 0,
                "cost_usd": 0.0,
            },
        )
        bucket_item["events"] += 1
        bucket_item["tokens"] += tokens
        bucket_item["cost_usd"] = round(bucket_item["cost_usd"] + total_cost, 6)

    summary["sessions"] = len(session_map)
    sessions = sorted(
        session_map.values(),
        key=lambda row: (float(row.get("cost_usd", 0.0)), int(row.get("tokens", 0))),
        reverse=True,
    )
    timeline = [timeline_map[k] for k in sorted(timeline_map)]
    n = max(1, min(limit, 500))

    return JSONResponse({
        "ok": True,
        "filters": {
            "session_id": clean_session,
            "period": period,
            "granularity": "hour" if use_hour else "day",
            "start": start_dt.isoformat() if start_dt else "",
            "end": end_dt.isoformat() if end_dt else "",
        },
        "summary": summary,
        "sessions": sessions,
        "timeline": timeline,
        "events": filtered[-n:],
    })


@app.get("/api/dashboard/logs")
def api_dashboard_logs(
    authorization: str | None = Header(default=None),
    limit: int = 100,
    level: str = Query(default=""),
    event: str = Query(default=""),
    q: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    n = max(1, min(limit, 500))
    rows = _filter_logs(list(LOG_RING), level=level, event=event, query=q)
    return JSONResponse({"ok": True, "logs": rows[-n:]})


@app.get("/api/hub/manifest")
def api_hub_manifest() -> JSONResponse:
    manifest = load_hub_manifest(_hub_manifest_path())
    return JSONResponse({"ok": True, "manifest": manifest})


@app.get("/api/hub/skills/{slug}")
def api_hub_skill(slug: str) -> JSONResponse:
    manifest = load_hub_manifest(_hub_manifest_path())
    for item in manifest.get("skills", []):
        if str(item.get("slug", "")).strip() == slug:
            return JSONResponse({"ok": True, "skill": item})
    raise HTTPException(status_code=404, detail="Skill not found")


@app.post("/api/hub/publish")
def api_hub_publish(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        result = publish_skill(
            payload.get("source_dir", ""),
            version=str(payload.get("version", "")).strip(),
            slug=payload.get("slug"),
            description=str(payload.get("description", "")),
            hub_dir=payload.get("hub_dir"),
            manifest_path=payload.get("manifest_path") or _hub_manifest_path(),
            download_base_url=str(payload.get("download_base_url", "")) or DEFAULT_DOWNLOAD_BASE_URL,
        )
    except SkillMarketplaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "result": result})


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != _token():
        await websocket.close(code=4403)
        return

    await websocket.accept()
    connections.add(websocket)
    await websocket.send_json({"type": "welcome", "service": "clawlite-gateway"})

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": _iso_now()})
            elif msg_type == "chat":
                session_id = str(msg.get("session_id") or "default")
                text = str(msg.get("text") or "").strip()
                try:
                    result = await _handle_chat_message(session_id=session_id, text=text)
                except HTTPException as exc:
                    await websocket.send_json({"type": "error", "detail": exc.detail})
                    continue
                await websocket.send_json(
                    {
                        "type": "chat",
                        "message": result["assistant_message"],
                        "meta": result["meta"],
                        "telemetry": result["telemetry"],
                    }
                )
            else:
                await websocket.send_json({"type": "echo", "payload": msg})
    except WebSocketDisconnect:
        pass
    finally:
        connections.discard(websocket)


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != _token():
        await websocket.close(code=4403)
        return
    await websocket.accept()
    chat_connections.add(websocket)
    await websocket.send_json({"type": "welcome", "channel": "chat"})

    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") != "chat":
                await websocket.send_json({"type": "error", "detail": "Use type=chat"})
                continue
            session_id = str(msg.get("session_id") or "default")
            text = str(msg.get("text") or "").strip()
            try:
                result = await _handle_chat_message(session_id=session_id, text=text)
            except HTTPException as exc:
                await websocket.send_json({"type": "error", "detail": exc.detail})
                continue
            await websocket.send_json(
                {
                    "type": "chat",
                    "message": result["assistant_message"],
                    "meta": result["meta"],
                    "telemetry": result["telemetry"],
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        chat_connections.discard(websocket)


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if token != _token():
        await websocket.close(code=4403)
        return
    level = str(websocket.query_params.get("level", "")).strip().lower()
    event = str(websocket.query_params.get("event", "")).strip().lower()
    query = str(websocket.query_params.get("q", "")).strip().lower()
    await websocket.accept()
    log_connections[websocket] = {"level": level, "event": event, "q": query}
    try:
        snapshot = _filter_logs(list(LOG_RING), level=level, event=event, query=query)
        await websocket.send_json({"type": "snapshot", "logs": snapshot[-100:]})
        while True:
            raw = await websocket.receive_text()
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "filters":
                continue
            level = str(payload.get("level", "")).strip().lower()
            event = str(payload.get("event", "")).strip().lower()
            query = str(payload.get("q", "")).strip().lower()
            log_connections[websocket] = {"level": level, "event": event, "q": query}
            snapshot = _filter_logs(list(LOG_RING), level=level, event=event, query=query)
            await websocket.send_json({"type": "snapshot", "logs": snapshot[-100:]})
    except WebSocketDisconnect:
        pass
    finally:
        log_connections.pop(websocket, None)


@app.get("/api/learning/stats")
async def api_learning_stats(
    period: str = Query("all", pattern="^(today|week|month|all)$"),
    skill: str | None = Query(None),
):
    from clawlite.runtime.learning import get_stats, get_templates
    from clawlite.runtime.preferences import get_preferences

    stats = get_stats(period=period, skill=skill)
    stats["preferences"] = get_preferences()
    stats["templates_count"] = sum(len(v) for v in get_templates().values())
    return JSONResponse(stats)


# ---------------------------------------------------------------------------
# Cron endpoints (paridade dashboard OpenClaw)
# ---------------------------------------------------------------------------

@app.get("/api/cron")
def api_cron_list(
    channel: str | None = Query(default=None),
    chat_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_bearer(authorization)
    jobs = list_cron_jobs(channel=channel, chat_id=chat_id)
    return JSONResponse({"ok": True, "jobs": [j.__dict__ for j in jobs]})


@app.post("/api/cron")
def api_cron_add(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        job_id = add_cron_job(
            channel=str(payload.get("channel", "telegram")),
            chat_id=str(payload.get("chat_id", "")),
            thread_id=str(payload.get("thread_id", "")),
            label=str(payload.get("label", "default")),
            name=str(payload.get("name", "")),
            text=str(payload.get("text", "")),
            interval_seconds=int(payload.get("interval_seconds", 3600)),
            enabled=bool(payload.get("enabled", True)),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log("cron.added", data={"id": job_id, "name": payload.get("name")})
    return JSONResponse({"ok": True, "id": job_id})


@app.delete("/api/cron/{job_id}")
def api_cron_remove(job_id: int, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    removed = remove_cron_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Cron job {job_id} não encontrado")
    _log("cron.removed", data={"id": job_id})
    return JSONResponse({"ok": True, "id": job_id})


# ---------------------------------------------------------------------------
# Channels status endpoint (paridade dashboard OpenClaw)
# ---------------------------------------------------------------------------

@app.get("/api/channels/status")
def api_channels_status(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    channels_cfg = cfg.get("channels", {})
    result: list[dict[str, Any]] = []
    for name, ch_cfg in channels_cfg.items():
        if not isinstance(ch_cfg, dict):
            continue
        enabled = bool(ch_cfg.get("enabled", False))
        has_token = bool(ch_cfg.get("token") or ch_cfg.get("accounts"))
        result.append({
            "channel": name,
            "enabled": enabled,
            "configured": has_token,
            "stt_enabled": bool(ch_cfg.get("stt_enabled", False)),
            "tts_enabled": bool(ch_cfg.get("tts_enabled", False)),
        })
    return JSONResponse({"ok": True, "channels": result})


# ---------------------------------------------------------------------------
# Config/channels/debug/update endpoints (paridade dashboard OpenClaw)
# ---------------------------------------------------------------------------


@app.put("/api/channels/config")
def api_channels_config_save(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    channels = payload.get("channels", {})
    if not isinstance(channels, dict):
        raise HTTPException(status_code=400, detail="Campo 'channels' deve ser objeto")

    clean_channels: dict[str, dict[str, Any]] = {}
    for name, raw in channels.items():
        if not isinstance(raw, dict):
            continue
        clean_channels[str(name)] = {
            "enabled": bool(raw.get("enabled", False)),
            "token": str(raw.get("token", "")).strip(),
            "account": str(raw.get("account", "")).strip(),
            "stt_enabled": bool(raw.get("stt_enabled", False)),
            "tts_enabled": bool(raw.get("tts_enabled", False)),
        }
    cfg["channels"] = clean_channels
    save_config(cfg)
    _log("channels.updated", data={"count": len(clean_channels)})
    return JSONResponse({"ok": True, "channels": clean_channels})


@app.post("/api/dashboard/config/apply")
def api_dashboard_config_apply(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    dry_run = bool(payload.get("dry_run", False))

    model = str(payload.get("model", cfg.get("model", ""))).strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model obrigatório")

    channels = payload.get("channels", cfg.get("channels", {}))
    if not isinstance(channels, dict):
        raise HTTPException(status_code=400, detail="Campo 'channels' inválido")

    sanitized_channels: dict[str, dict[str, Any]] = {}
    for name, raw in channels.items():
        if not isinstance(raw, dict):
            continue
        sanitized_channels[str(name)] = {
            "enabled": bool(raw.get("enabled", False)),
            "token": str(raw.get("token", "")).strip(),
            "account": str(raw.get("account", "")).strip(),
            "stt_enabled": bool(raw.get("stt_enabled", False)),
            "tts_enabled": bool(raw.get("tts_enabled", False)),
        }

    pending_cfg = dict(cfg)
    pending_cfg["model"] = model
    pending_cfg["channels"] = sanitized_channels

    if not dry_run:
        save_config(pending_cfg)
        _log("config.applied", data={"model": model, "channels": len(sanitized_channels)})
    else:
        _log("config.apply.dry_run", data={"model": model, "channels": len(sanitized_channels)})

    return JSONResponse(
        {
            "ok": True,
            "dry_run": dry_run,
            "settings": {
                "model": model,
                "channels": sanitized_channels,
            },
            "message": "validação concluída" if dry_run else "config aplicada",
        }
    )


@app.post("/api/dashboard/config/restart")
def api_dashboard_config_restart(payload: dict[str, Any] | None = None, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    mode = "safe"
    if isinstance(payload, dict):
        mode = str(payload.get("mode", "safe")).strip() or "safe"
    _log("gateway.restart.requested", data={"mode": mode})
    return JSONResponse(
        {
            "ok": True,
            "mode": mode,
            "performed": False,
            "message": "Restart seguro registrado (noop no runtime embutido)",
        }
    )


@app.get("/api/dashboard/debug")
def api_dashboard_debug(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse(
        {
            "ok": True,
            "debug": {
                "version": _version(),
                "python": sys.version.split(" ")[0],
                "platform": platform.platform(),
                "cwd": str(Path.cwd()),
                "home": str(Path.home()),
                "config_dir": str(CONFIG_DIR),
                "skills_dir": str(_skills_dir()),
                "logs_in_ring": len(LOG_RING),
                "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
            },
        }
    )


@app.post("/api/dashboard/update")
def api_dashboard_update(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slugs = payload.get("slugs") or []
    if not isinstance(slugs, list):
        raise HTTPException(status_code=400, detail="Campo 'slugs' deve ser lista")
    dry_run = bool(payload.get("dry_run", True))
    try:
        result = update_skills(slugs=[str(s) for s in slugs], dry_run=dry_run)
    except SkillMarketplaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log("skills.update", data={"dry_run": dry_run, "count": len(result.get("updated", []))})
    return JSONResponse({"ok": True, "dry_run": dry_run, "result": result})


# ---------------------------------------------------------------------------
# Metrics endpoint (observabilidade P0)
# ---------------------------------------------------------------------------

@app.get("/api/metrics")
def api_metrics(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    from clawlite.runtime.multiagent import list_workers, DB_PATH
    import sqlite3 as _sqlite3

    workers = list_workers()
    running_workers = [w for w in workers if w.status == "running" and w.pid]

    queued_tasks = 0
    running_tasks = 0
    if DB_PATH.exists():
        try:
            with _sqlite3.connect(DB_PATH) as c:
                queued_tasks = c.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status='queued'"
                ).fetchone()[0]
                running_tasks = c.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status='running'"
                ).fetchone()[0]
        except _sqlite3.Error:
            pass

    uptime_s = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    total_logs = len(LOG_RING)
    error_logs = sum(1 for e in LOG_RING if e.get("level") == "error")
    warn_logs = sum(1 for e in LOG_RING if e.get("level") == "warn")

    return JSONResponse({
        "ok": True,
        "uptime_seconds": round(uptime_s, 1),
        "workers": {
            "total": len(workers),
            "running": len(running_workers),
        },
        "tasks": {
            "queued": queued_tasks,
            "running": running_tasks,
        },
        "log_ring": {
            "total": total_logs,
            "errors": error_logs,
            "warnings": warn_logs,
        },
        "websocket_connections": {
            "ws": len(connections),
            "chat": len(chat_connections),
            "logs": len(log_connections),
        },
    })


def run_gateway(host: str | None = None, port: int | None = None) -> None:
    cfg = load_config()
    h_raw = host if host is not None else cfg.get("gateway", {}).get("host", "0.0.0.0")
    h = str(h_raw).strip() or "0.0.0.0"

    p_raw = port if port is not None else cfg.get("gateway", {}).get("port", 8787)
    try:
        p = int(p_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Configuração inválida do gateway: 'port' deve ser inteiro entre 1 e 65535."
        ) from exc
    if p < 1 or p > 65535:
        raise RuntimeError(
            f"Configuração inválida do gateway: porta {p} fora do intervalo 1..65535."
        )

    _log("gateway.started", data={"host": h, "port": p})

    # Inicia heartbeat em thread daemon (para quando o processo encerra)
    hb_interval = int(cfg.get("gateway", {}).get("heartbeat_interval_s", 1800))
    from clawlite.core.heartbeat import start_heartbeat_thread
    start_heartbeat_thread(interval_s=hb_interval)

    try:
        uvicorn.run(
            app,
            host=h,
            port=p,
            access_log=False,
            log_level="warning",
        )
    except OSError as exc:
        raise RuntimeError(
            f"Falha ao iniciar gateway em {h}:{p}. Verifique porta em uso/permissão. Detalhe: {exc}"
        ) from exc
