from __future__ import annotations

import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from clawlite.config.settings import load_config, save_config

PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "display": "OpenAI",
        "auth_url": "https://platform.openai.com/api-keys",
        "note": "OpenAI não expõe OAuth público padrão para API. Abra a página e gere/paste token.",
    },
    "anthropic": {
        "display": "Anthropic",
        "auth_url": "https://console.anthropic.com/settings/keys",
        "note": "Anthropic não expõe OAuth público padrão para API. Abra a página e gere/paste token.",
    },
    "gemini": {
        "display": "Google Gemini",
        "auth_url": "https://aistudio.google.com/app/apikey",
        "note": "Gemini API usa chave; abra a página e gere/paste token.",
    },
    "openrouter": {
        "display": "OpenRouter",
        "auth_url": "https://openrouter.ai/keys",
        "note": "OpenRouter usa chave; abra a página e gere/paste token.",
    },
    "groq": {
        "display": "Groq",
        "auth_url": "https://console.groq.com/keys",
        "note": "Groq usa chave; abra a página e gere/paste token.",
    },
}


def _cfg_auth(cfg: dict) -> dict:
    cfg.setdefault("auth", {})
    cfg["auth"].setdefault("providers", {})
    return cfg


def auth_status() -> list[dict[str, Any]]:
    cfg = _cfg_auth(load_config())
    out = []
    for k, meta in PROVIDERS.items():
        tok = cfg["auth"]["providers"].get(k, {}).get("token", "")
        out.append({"provider": k, "display": meta["display"], "logged_in": bool(tok)})
    return out


def auth_logout(provider: str) -> bool:
    p = provider.lower()
    cfg = _cfg_auth(load_config())
    if p in cfg["auth"]["providers"]:
        cfg["auth"]["providers"].pop(p, None)
        save_config(cfg)
        return True
    return False


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] = {}

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        token = qs.get("token", [""])[0] or qs.get("code", [""])[0]
        if token:
            _CallbackHandler.result = {"token": token}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ClawLite auth success. You can close this tab.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing token/code.")

    def log_message(self, format, *args):  # noqa: A003
        return


def _try_local_callback(timeout_seconds: int = 120) -> str:
    port = 8765
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    _CallbackHandler.result = {}

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    for _ in range(timeout_seconds):
        if _CallbackHandler.result.get("token"):
            server.shutdown()
            return _CallbackHandler.result["token"]
        import time
        time.sleep(1)
    server.shutdown()
    return ""


def auth_login(provider: str, non_interactive_token: str | None = None) -> tuple[bool, str]:
    p = provider.lower()
    if p not in PROVIDERS:
        return False, f"Provider não suportado: {provider}"

    meta = PROVIDERS[p]
    cfg = _cfg_auth(load_config())

    state = secrets.token_urlsafe(16)
    callback = "http://127.0.0.1:8765/callback"
    auth_url = f"{meta['auth_url']}?state={state}&redirect_uri={urllib.parse.quote(callback)}"

    print(f"\n🔐 Iniciando login em {meta['display']}")
    print(f"URL de autorização: {auth_url}")
    print(meta["note"])

    token = non_interactive_token or ""
    if not token:
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass
        print("\nSe o provedor suportar callback com token/code, aguarde captura automática...\n")
        token = _try_local_callback(timeout_seconds=25)

    if not token:
        token = os.getenv(f"CLAWLITE_{p.upper()}_TOKEN", "").strip()

    if not token:
        token = input("Cole o token/chave do provedor: ").strip()

    if not token:
        return False, "Token não informado."

    cfg["auth"]["providers"][p] = {
        "token": token,
        "saved_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    save_config(cfg)
    return True, f"Login salvo para {meta['display']}"
