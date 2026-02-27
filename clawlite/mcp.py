from __future__ import annotations

import importlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from clawlite.skills.registry import SKILLS, describe_skill

MCP_CONFIG_PATH = Path.home() / ".clawlite" / "mcp.json"
MCP_CATALOG_URL = "https://raw.githubusercontent.com/modelcontextprotocol/servers/main/README.md"

KNOWN_SERVER_TEMPLATES: dict[str, dict[str, str]] = {
    "filesystem": {
        "name": "filesystem",
        "url": "npx -y @modelcontextprotocol/server-filesystem ~/",
        "description": "Servidor MCP para acesso ao filesystem local.",
    },
    "github": {
        "name": "github",
        "url": "npx -y @modelcontextprotocol/server-github",
        "description": "Servidor MCP para operações no GitHub (exige token).",
    },
}


def _default_config() -> dict[str, Any]:
    return {"servers": {}}


def _normalize_name(name: str) -> str:
    value = name.strip().lower()
    if not value:
        raise ValueError("Nome do servidor é obrigatório")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", value):
        raise ValueError("Nome inválido. Use apenas letras minúsculas, números, ponto, _ e -")
    return value


def _validate_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ValueError("URL/comando do servidor é obrigatório")
    if value.startswith(("http://", "https://", "ws://", "wss://", "npx ", "uvx ", "python ", "node ")):
        return value
    raise ValueError("URL/comando inválido. Use http(s)/ws(s) ou comando (npx/uvx/python/node)")


def load_mcp_config(path: Path | None = None) -> dict[str, Any]:
    target = path or MCP_CONFIG_PATH
    if not target.exists():
        return _default_config()
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return _default_config()
    servers = raw.get("servers")
    if not isinstance(servers, dict):
        raw["servers"] = {}
    return raw


def save_mcp_config(config: dict[str, Any], path: Path | None = None) -> Path:
    target = path or MCP_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def list_servers(path: Path | None = None) -> list[dict[str, str]]:
    cfg = load_mcp_config(path)
    out: list[dict[str, str]] = []
    for name, url in sorted(cfg.get("servers", {}).items()):
        out.append({"name": str(name), "url": str(url)})
    return out


def add_server(name: str, url: str, path: Path | None = None) -> dict[str, str]:
    n = _normalize_name(name)
    u = _validate_url(url)
    cfg = load_mcp_config(path)
    cfg.setdefault("servers", {})[n] = u
    save_mcp_config(cfg, path)
    return {"name": n, "url": u}


def remove_server(name: str, path: Path | None = None) -> bool:
    n = _normalize_name(name)
    cfg = load_mcp_config(path)
    servers = cfg.setdefault("servers", {})
    if n not in servers:
        return False
    del servers[n]
    save_mcp_config(cfg, path)
    return True


def _parse_catalog_markdown(md: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in md.splitlines():
        if "|" not in line or "github.com" not in line.lower():
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 2:
            continue
        name = re.sub(r"[`*]", "", cols[0]).strip().lower()
        repo = cols[1]
        if not name or name in {"name", "server"}:
            continue
        rows.append({"name": name, "source": repo, "description": cols[2] if len(cols) > 2 else ""})
    dedup: dict[str, dict[str, str]] = {}
    for row in rows:
        dedup[row["name"]] = row
    return sorted(dedup.values(), key=lambda r: r["name"])


def search_marketplace(query: str = "") -> list[dict[str, str]]:
    q = query.strip().lower()
    results: dict[str, dict[str, str]] = {
        k: {"name": v["name"], "source": "template", "description": v["description"]}
        for k, v in KNOWN_SERVER_TEMPLATES.items()
    }
    try:
        req = urllib.request.Request(MCP_CATALOG_URL, headers={"User-Agent": "clawlite/0.4"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            md = resp.read().decode("utf-8", errors="ignore")
        for row in _parse_catalog_markdown(md):
            results.setdefault(row["name"], row)
    except (urllib.error.URLError, TimeoutError, ValueError):
        pass

    rows = list(results.values())
    if q:
        rows = [r for r in rows if q in r["name"].lower() or q in r.get("description", "").lower()]
    return sorted(rows, key=lambda r: r["name"])[:100]


def install_template(name: str, path: Path | None = None) -> dict[str, str]:
    key = _normalize_name(name)
    tpl = KNOWN_SERVER_TEMPLATES.get(key)
    if not tpl:
        raise ValueError(f"Template MCP não suportado: {name}")
    return add_server(tpl["name"], tpl["url"], path)


def mcp_tools_from_skills() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for slug in sorted(SKILLS.keys()):
        tools.append(
            {
                "name": f"skill.{slug}",
                "description": describe_skill(slug),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Comando/texto de entrada para a skill"},
                        "prompt": {"type": "string", "description": "Alias para command"},
                    },
                    "additionalProperties": True,
                },
            }
        )
    return tools


def dispatch_skill_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    if not tool_name.startswith("skill."):
        raise ValueError("Tool MCP inválida. Use prefixo skill.")
    slug = tool_name.split(".", 1)[1]
    entry = SKILLS.get(slug)
    if not entry:
        raise ValueError(f"Skill não encontrada: {slug}")

    mod_name, fn_name = entry.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name)

    command = args.get("command") or args.get("prompt") or ""
    if not isinstance(command, str):
        command = json.dumps(command, ensure_ascii=False)

    try:
        result = fn(command)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Erro ao executar skill '{slug}': {exc}") from exc

    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }
