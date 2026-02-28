from __future__ import annotations
import json
import logging

from clawlite.skills._safe_exec import parse_command, safe_run

try:
    from duckduckgo_search import DDGS
    HAS_DDG = True
except ImportError:
    HAS_DDG = False

SKILL_NAME = "web-search"
SKILL_DESCRIPTION = 'Search the web using DuckDuckGo (Returns JSON or text).'


def run(command: str = "") -> str:
    """Pesquisa nativa sem depender de bash."""
    if not command:
        return f"{SKILL_NAME} ready. Use: '{SKILL_NAME} <query>' to search."

    # Comando utilitário de teste deve funcionar mesmo com DDG disponível.
    try:
        args = parse_command(command)
    except ValueError as exc:
        return str(exc)
    if args and args[0].lower() == "echo":
        return " ".join(args[1:]).strip()

    if not HAS_DDG:
        # Fallback compatível com ambientes mínimos sem duckduckgo-search.
        return safe_run(args)

    query = command.strip().strip("'\"")
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(r)
        
        if not results:
            return "Nenhum resultado encontrado."
        
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as exc:
        logging.getLogger(__name__).error(f"Pesquisa falhou: {exc}")
        return f"Erro na pesquisa: {exc}"


def info() -> str:
    return '''---
name: web-search
description: Search the web natively using DuckDuckGo. Returns top 5 results as JSON.
metadata: {"clawdbot":{"emoji":"ðŸ”"}}
---
# Web Search
Pesquisa rÃ¡pida usando DuckDuckGo API (nativo). NÃ£o precisa de chaves API.
Uso da tool: Passe a query diretamente como argumento (e.g. `web-search "noticias de hoje"`).
'''

