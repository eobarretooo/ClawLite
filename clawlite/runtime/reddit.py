from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from clawlite.config.settings import load_config, save_config

REDDIT_AUTH_BASE = "https://www.reddit.com/api/v1/authorize"
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_BASE = "https://oauth.reddit.com"

DEFAULT_SUBREDDITS = ["selfhosted", "Python", "AIAssistants", "termux"]
DEFAULT_UA = "clawlite/0.4.0 by u/eobarretooo"

STATE_PATH = Path.home() / ".clawlite" / "reddit_state.json"


def _cfg(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    cfg.setdefault("reddit", {})
    r = cfg["reddit"]
    r.setdefault("enabled", False)
    r.setdefault("client_id", "")
    r.setdefault("client_secret", "")
    r.setdefault("redirect_uri", "http://127.0.0.1:8788/reddit/callback")
    r.setdefault("refresh_token", "")
    r.setdefault("subreddits", DEFAULT_SUBREDDITS)
    r.setdefault("notify_chat_id", "")
    return cfg


def reddit_status() -> dict[str, Any]:
    cfg = _cfg()
    r = cfg["reddit"]
    return {
        "enabled": r.get("enabled", False),
        "client_id": bool(r.get("client_id")),
        "client_secret": bool(r.get("client_secret")),
        "refresh_token": bool(r.get("refresh_token")),
        "subreddits": r.get("subreddits", DEFAULT_SUBREDDITS),
        "redirect_uri": r.get("redirect_uri"),
    }


def auth_url(scopes: str = "identity submit read history") -> str:
    cfg = _cfg()
    r = cfg["reddit"]
    params = {
        "client_id": r.get("client_id", ""),
        "response_type": "code",
        "state": "clawlite_reddit_auth",
        "redirect_uri": r.get("redirect_uri", "http://127.0.0.1:8788/reddit/callback"),
        "duration": "permanent",
        "scope": scopes,
    }
    return f"{REDDIT_AUTH_BASE}?{urllib.parse.urlencode(params)}"


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    import base64

    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("utf-8")


def exchange_code(code: str) -> dict[str, Any]:
    cfg = _cfg()
    r = cfg["reddit"]
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": r["redirect_uri"],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        REDDIT_TOKEN_URL,
        data=data,
        headers={
            "Authorization": _basic_auth_header(r["client_id"], r["client_secret"]),
            "User-Agent": DEFAULT_UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    refresh = payload.get("refresh_token", "")
    if refresh:
        cfg["reddit"]["refresh_token"] = refresh
        cfg["reddit"]["enabled"] = True
        save_config(cfg)
    return payload


def _access_token() -> str:
    cfg = _cfg()
    r = cfg["reddit"]
    data = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": r["refresh_token"]}).encode("utf-8")
    req = urllib.request.Request(
        REDDIT_TOKEN_URL,
        data=data,
        headers={
            "Authorization": _basic_auth_header(r["client_id"], r["client_secret"]),
            "User-Agent": DEFAULT_UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    token = payload.get("access_token", "")
    if not token:
        raise RuntimeError("Falha ao obter access token Reddit")
    return token


def _api_request(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    tok = _access_token()
    data = None
    headers = {"Authorization": f"Bearer {tok}", "User-Agent": DEFAULT_UA}
    if body is not None:
        data = urllib.parse.urlencode(body).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(f"{REDDIT_API_BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def post_milestone(title: str, text: str, subreddits: list[str] | None = None) -> list[dict[str, Any]]:
    targets = subreddits or _cfg()["reddit"].get("subreddits", DEFAULT_SUBREDDITS)
    out = []
    for sub in targets:
        payload = _api_request(
            "/api/submit",
            method="POST",
            body={"sr": sub, "kind": "self", "title": title, "text": text, "resubmit": True},
        )
        out.append({"subreddit": sub, "response": payload})
        time.sleep(1)
    return out


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"seen": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _suggest_reply(text: str, author: str) -> str:
    t = (text or "").lower()
    if "?" in t:
        return f"Valeu pela pergunta, u/{author}! Posso detalhar o roadmap e compartilhar o trecho técnico mais relevante dessa milestone."
    if any(k in t for k in ["cool", "nice", "parabéns", "great", "awesome"]):
        return f"Obrigado pelo feedback, u/{author}! Estamos evoluindo rápido e vamos publicar os próximos benchmarks em breve."
    return f"Obrigado por comentar, u/{author}! Se quiser, eu compartilho os detalhes da implementação dessa parte no próximo update."


def _telegram_send(text: str) -> None:
    cfg = _cfg()
    tg = cfg.get("channels", {}).get("telegram", {})
    token = tg.get("token", "")
    chat_id = cfg["reddit"].get("notify_chat_id", "") or (tg.get("allowFrom", [""])[0] if tg.get("allowFrom") else "")
    if not token or not chat_id:
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=30):
        pass


def monitor_mentions_once() -> dict[str, Any]:
    # Busca comentários recentes com "clawlite" nos subreddits alvo
    cfg = _cfg()
    subs = cfg["reddit"].get("subreddits", DEFAULT_SUBREDDITS)
    state = _load_state()
    seen = set(state.get("seen", []))
    new_items = []

    for sub in subs:
        data = _api_request(f"/r/{sub}/comments.json?limit=25&sort=new")
        children = data.get("data", {}).get("children", [])
        for c in children:
            d = c.get("data", {})
            cid = d.get("id")
            body = (d.get("body") or "")
            if not cid or cid in seen:
                continue
            if "clawlite" not in body.lower():
                continue
            seen.add(cid)
            author = d.get("author", "user")
            suggestion = _suggest_reply(body, author)
            msg = (
                "💬 Menção ao ClawLite no Reddit\n\n"
                f"Subreddit: r/{sub}\n"
                f"Autor: u/{author}\n"
                f"Comentário: {body[:600]}\n\n"
                f"Sugestão de resposta:\n{suggestion}\n\n"
                "Aprova antes de responder."
            )
            _telegram_send(msg)
            new_items.append({"id": cid, "subreddit": sub, "author": author, "body": body, "suggestion": suggestion})

    state["seen"] = sorted(list(seen))[-1000:]
    _save_state(state)
    return {"checked_subreddits": subs, "new_mentions": len(new_items), "items": new_items}
