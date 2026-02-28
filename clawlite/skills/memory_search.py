from __future__ import annotations
import os
import json
from pathlib import Path

SKILL_NAME = "memory-search"
SKILL_DESCRIPTION = 'Busca anotações na pasta ~/.clawlite/workspace/memory'


def run(command: str = "") -> str:
    """Busca burra de substring nos markdowns/jsons do workspace/memory."""
    if not command:
        return f"{SKILL_NAME} ready. Use: '{SKILL_NAME} <query>' to search memory."

    query = command.strip().strip("'\"").lower()
    memory_dir = Path.home() / ".clawlite" / "workspace" / "memory"
    
    if not memory_dir.exists():
        return "O diretório de memória ainda não existe."

    results = []
    
    try:
        for file in memory_dir.rglob("*"):
            if not file.is_file() or file.suffix not in [".md", ".json", ".txt"]:
                continue
            
            try:
                content = file.read_text(encoding="utf-8")
                if query in content.lower():
                    # Extrair contexto: pegar 50 chars antes e depois
                    idx = content.lower().find(query)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(query) + 50)
                    snippet = content[start:end].replace("\n", " ").strip()
                    results.append({
                        "file": str(file.relative_to(memory_dir)),
                        "snippet": f"...{snippet}..."
                    })
            except Exception:
                continue

        if not results:
            return f"Nenhuma memória encontrada para: {query}"
        
        return json.dumps(results[:10], indent=2, ensure_ascii=False)
            
    except Exception as exc:
        return f"Falha na busca da memória: {exc}"


def info() -> str:
    return '''---
name: memory-search
description: Busca arquivos de memória e anotações armazenadas pelo ClawLite.
metadata: {"clawdbot":{"emoji":"🧠"}}
---
# Memory Search
Analisa as últimas anotações do agente na pasta local de workspace memory. 
Uso da tool: Passe a query diretamente (e.g. `memory-search "chave de api"`).
'''
