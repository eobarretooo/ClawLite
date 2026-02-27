from __future__ import annotations

import json
import os
import re
import secrets
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from clawlite.config.settings import CONFIG_DIR, load_config, save_config
from clawlite.skills.marketplace import (
    DEFAULT_DOWNLOAD_BASE_URL,
    SkillMarketplaceError,
    load_hub_manifest,
    publish_skill,
)

app = FastAPI(title="ClawLite Gateway", version="0.3.0")
connections: set[WebSocket] = set()
chat_connections: set[WebSocket] = set()
log_connections: set[WebSocket] = set()
STARTED_AT = datetime.now(timezone.utc)

LOG_RING: deque[dict[str, Any]] = deque(maxlen=500)


DASHBOARD_DIR = CONFIG_DIR / "dashboard"
SESSIONS_FILE = DASHBOARD_DIR / "sessions.jsonl"
TELEMETRY_FILE = DASHBOARD_DIR / "telemetry.jsonl"
SETTINGS_FILE = DASHBOARD_DIR / "settings.json"


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


def _estimate_cost_usd(tokens: int, model: str) -> float:
    # estimativa local simplificada por 1K tokens
    cheap_models = ("mini", "flash", "haiku")
    rate_per_1k = 0.002 if any(x in model.lower() for x in cheap_models) else 0.01
    return round((tokens / 1000.0) * rate_per_1k, 6)


def _log(event: str, level: str = "info", data: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "ts": _iso_now(),
        "level": level,
        "event": event,
        "data": data or {},
    }
    LOG_RING.append(entry)
    for ws in list(log_connections):
        try:
            import asyncio
            asyncio.create_task(ws.send_json({"type": "log", "payload": entry}))
        except Exception:
            log_connections.discard(ws)
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "clawlite-gateway",
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "connections": len(connections) + len(chat_connections) + len(log_connections),
    }


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
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        skill_file.write_text(f"# {slug}\n\nSkill local instalada via dashboard.\n", encoding="utf-8")

    cfg = load_config()
    active = set(cfg.get("skills", []))
    active.add(slug)
    cfg["skills"] = sorted(active)
    save_config(cfg)
    _log("skills.installed", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug})


@app.post("/api/dashboard/skills/enable")
def api_dashboard_skills_enable(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    cfg = load_config()
    active = set(cfg.get("skills", []))
    active.add(slug)
    cfg["skills"] = sorted(active)
    save_config(cfg)
    _log("skills.enabled", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug})


@app.post("/api/dashboard/skills/disable")
def api_dashboard_skills_disable(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    cfg = load_config()
    cfg["skills"] = [s for s in cfg.get("skills", []) if s != slug]
    save_config(cfg)
    _log("skills.disabled", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug})


@app.post("/api/dashboard/skills/remove")
def api_dashboard_skills_remove(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))

    cfg = load_config()
    cfg["skills"] = [s for s in cfg.get("skills", []) if s != slug]
    save_config(cfg)

    skill_dir = _skills_dir() / slug
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
    return JSONResponse({"ok": True, "slug": slug})


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
def api_dashboard_telemetry(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    rows = _read_jsonl(TELEMETRY_FILE)
    total_tokens = sum(int(i.get("tokens", 0)) for i in rows)
    total_cost_usd = round(sum(float(i.get("cost_usd", 0.0)) for i in rows), 6)
    return JSONResponse({
        "ok": True,
        "summary": {
            "events": len(rows),
            "tokens": total_tokens,
            "cost_usd": total_cost_usd,
        },
        "events": rows[-100:],
    })


@app.get("/api/dashboard/logs")
def api_dashboard_logs(authorization: str | None = Header(default=None), limit: int = 100) -> JSONResponse:
    _check_bearer(authorization)
    n = max(1, min(limit, 500))
    return JSONResponse({"ok": True, "logs": list(LOG_RING)[-n:]})


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
                cfg = load_config()
                model = cfg.get("model", "openai/gpt-4o-mini")
                user_msg = {"ts": _iso_now(), "session_id": session_id, "role": "user", "text": text}
                _append_jsonl(SESSIONS_FILE, user_msg)

                reply = f"[{model}] Resposta local (MVP): recebi '{text}'"
                assistant_msg = {"ts": _iso_now(), "session_id": session_id, "role": "assistant", "text": reply}
                _append_jsonl(SESSIONS_FILE, assistant_msg)

                tokens = _estimate_tokens(text) + _estimate_tokens(reply)
                cost_usd = _estimate_cost_usd(tokens, model)
                _append_jsonl(TELEMETRY_FILE, {
                    "ts": _iso_now(),
                    "session_id": session_id,
                    "model": model,
                    "tokens": tokens,
                    "cost_usd": cost_usd,
                })
                _log("chat.message", data={"session_id": session_id, "tokens": tokens, "cost_usd": cost_usd})
                await websocket.send_json({"type": "chat", "message": assistant_msg})
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
            cfg = load_config()
            model = cfg.get("model", "openai/gpt-4o-mini")

            user_msg = {"ts": _iso_now(), "session_id": session_id, "role": "user", "text": text}
            _append_jsonl(SESSIONS_FILE, user_msg)

            reply = f"[{model}] Resposta local (MVP): recebi '{text}'"
            assistant_msg = {"ts": _iso_now(), "session_id": session_id, "role": "assistant", "text": reply}
            _append_jsonl(SESSIONS_FILE, assistant_msg)

            tokens = _estimate_tokens(text) + _estimate_tokens(reply)
            cost_usd = _estimate_cost_usd(tokens, model)
            _append_jsonl(TELEMETRY_FILE, {
                "ts": _iso_now(),
                "session_id": session_id,
                "model": model,
                "tokens": tokens,
                "cost_usd": cost_usd,
            })
            _log("chat.message", data={"session_id": session_id, "tokens": tokens, "cost_usd": cost_usd})

            await websocket.send_json({"type": "chat", "message": assistant_msg})
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
    await websocket.accept()
    log_connections.add(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "logs": list(LOG_RING)[-100:]})
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        log_connections.discard(websocket)


def run_gateway(host: str | None = None, port: int | None = None) -> None:
    cfg = load_config()
    h = host or cfg.get("gateway", {}).get("host", "0.0.0.0")
    p = port or int(cfg.get("gateway", {}).get("port", 8787))
    _log("gateway.started", data={"host": h, "port": p})
    uvicorn.run(app, host=h, port=p)
