from __future__ import annotations

import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from clawlite.config.settings import load_config, save_config
from clawlite.core.providers import get_provider_spec, normalize_provider

_AUTH_PROVIDER_KEYS = (
    "openai",
    "anthropic",
    "gemini",
    "openrouter",
    "groq",
    "moonshot",
    "mistral",
    "xai",
    "together",
    "huggingface",
    "nvidia",
    "qianfan",
    "venice",
    "minimax",
    "xiaomi",
    "zai",
    "litellm",
    "vercel-ai-gateway",
    "kilocode",
    "vllm",
)


def _build_providers() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key in _AUTH_PROVIDER_KEYS:
        spec = get_provider_spec(key)
        if not spec:
            continue
        out[key] = {
            "display": spec.display,
            "auth_url": spec.auth_url,
            "note": spec.note,
            "env_vars": spec.env_vars,
            # API-key based providers: callback usually does not exist.
            "supports_callback": False,
        }
    return out


PROVIDERS: dict[str, dict[str, Any]] = _build_providers()


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
    p = normalize_provider(provider)
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
            self.wfile.write("Autenticação ClawLite concluída. Pode fechar esta aba.".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("Token/código ausente.".encode("utf-8"))

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
    p = normalize_provider(provider)
    if p not in PROVIDERS:
        return False, f"Provider não suportado: {provider}"

    meta = PROVIDERS[p]
    cfg = _cfg_auth(load_config())

    supports_callback = bool(meta.get("supports_callback", False))
    auth_url = str(meta["auth_url"])
    if supports_callback:
        state = secrets.token_urlsafe(16)
        callback = "http://127.0.0.1:8765/callback"
        auth_url = f"{auth_url}?state={state}&redirect_uri={urllib.parse.quote(callback)}"

    print(f"\n🔐 Iniciando login em {meta['display']}")
    print(f"URL de autorização: {auth_url}")
    print(meta["note"])
    env_vars = meta.get("env_vars", ())
    if isinstance(env_vars, tuple) and env_vars:
        print(f"Env vars aceitas: {', '.join(env_vars)}")

    token = non_interactive_token or ""
    if not token:
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass
        if supports_callback:
            print("\nAguardando callback automático...\n")
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
