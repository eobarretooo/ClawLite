from __future__ import annotations

import httpx
import logging

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

SKILL_NAME = "web-fetch"
SKILL_DESCRIPTION = 'Extrair texto limpo de páginas web.'


def run(command: str = "") -> str:
    """Extração de página nativa via HTTPx e convertida a texto limpo por bs4."""
    if not command:
        return f"{SKILL_NAME} ready. Use: '{SKILL_NAME} <url>' to fetch."

    if not HAS_BS4:
        return "Erro: beautifulsoup4 não está instalado. Rode: pip install beautifulsoup4"
    
    url = command.strip().strip("'\"")
    if not url.startswith("http"):
        url = "https://" + url

    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(
                url, 
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Remover scripts e styles
            for script in soup(["script", "style", "nav", "footer", "aside"]):
                script.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            # Limpa excesso de espaços
            clean_text = ' '.join(text.split())
            
            # Retorna no máximo os primeiros 10 mil caracteres para não estourar contexto
            if len(clean_text) > 10000:
                clean_text = clean_text[:10000] + "\n... [truncado]"
                
            return clean_text
    except Exception as exc:
        logging.getLogger(__name__).error(f"Fetch falhou para {url}: {exc}")
        return f"Erro ao acessar {url}: {exc}"


def info() -> str:
    return '''---
name: web-fetch
description: Extrai texto limpo de qualquer URL usando Python nativo.
metadata: {"clawdbot":{"emoji":"🕸️"}}
---
# Web Fetch
Baixa uma URL e usa BeautifulSoup para retornar texto limpo de conteúdo web (sem scripts e footer).
Uso da tool: Passe a URL diretamente (e.g. `web-fetch "https://exemplo.com"`).
'''
