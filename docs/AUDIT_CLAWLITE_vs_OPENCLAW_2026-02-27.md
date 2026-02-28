# AUDITORIA TÉCNICA SÊNIOR: ClawLite v0.4.1 vs OpenClaw
**Data:** 2026-02-27
**Auditor:** Claude Sonnet 4.6 (análise de código-fonte + documentação pública)
**Metodologia:** Leitura direta de código + fetch de docs oficiais + comparação funcional

---

## A) EXECUTIVE SUMMARY

ClawLite v0.4.1 é um projeto de agente de IA com fundação técnica real e bem estruturada:
gateway FastAPI/WebSocket funcional, sistema de memória em múltiplas camadas (markdown + SQLite),
learning loop com retry inteligente, marketplace de skills com validação SHA256 e rollback,
orquestração multi-agente em SQLite com routing por menção/tag, e MCP server JSON-RPC 2.0
exposto via gateway. O código é limpo, modular e tem 17 arquivos de teste (~1.731 linhas).
Há também CI parcial (secret-scan + docs).

**Porém, existem gaps críticos de produção:**
- `run_remote_provider` em `offline.py` é **STUB** — retorna f-string, não chama API real de LLM
- Integração de canais usa `subprocess.run(shell=True)` com command_template (frágil + inseguro)
- "Busca semântica" é keyword matching simples sem embeddings
- Dashboard não tem cron panel, channel status com QR, streaming, device pairing, exec approval
- 23/37 skills em status "dev", hub manifest pode estar vazio em produção

**Veredito: AINDA DISTANTE — ~35–40% de paridade com OpenClaw em poder real de operação.**

---

## B) SCORECARD (0–10 por área)

| Área                    | Nota  | Justificativa técnica |
|-------------------------|-------|----------------------|
| Installer/Onboarding    | 6/10  | install.sh com auto-detecção Termux, venv, bootstrap, PATH fix. Wizard 9 etapas. Sem Windows/macOS, daemon, migration guide |
| Gateway/Dashboard       | 5/10  | FastAPI + 3 WS endpoints + 20+ REST. Telemetry com cost breakdown, logs filtráveis. Sem streaming, hot-reload, cron UI, device pairing, exec approval |
| Multi-agent/Channels    | 4/10  | Agents/bindings em SQLite, routing por menção/tag, recover_workers(). Mas canais via shell=True. Provider é stub. Sem reconexão automática |
| Skills/Marketplace      | 5/10  | SHA256, allowlist, rollback, path traversal check. 37 skills (23 em dev). Hub manifest pode estar vazio. 37 vs 5700+ OpenClaw |
| Memory/Learning         | 6/10  | 5 MD files + daily log + compactação automática. Learning DB com retry, template learning, WAL. "Semantic" é keyword scoring |
| MCP                     | 6/10  | JSON-RPC 2.0 completo: initialize, tools/list, tools/call. Skills como tools. 2 templates via npx (contradiz "sem Node.js") |
| Security/Operations     | 4/10  | URL allowlist + SHA256, secret-scan CI, SECURITY.md. Mas shell=True, provider stub, token em JSON plain, sem backup/restore, sem runbook |

---

## C) TABELA DE PARIDADE COM OPENCLAW

| Feature                          | OpenClaw | ClawLite          | Gap             | Esforço |
|----------------------------------|----------|-------------------|-----------------|---------|
| Installer curl one-liner         | ✅       | ✅                | —               | —       |
| Auto-detect ambiente             | ✅ npm   | ✅ Termux/Linux   | Escopo diferente| —       |
| Windows suporte                  | ✅       | ❌                | Real            | M       |
| Daemon / auto-start              | ✅       | ❌                | Real            | M       |
| Onboarding wizard                | ✅       | ✅                | —               | —       |
| Gateway HTTP                     | ✅ 18789 | ✅ 8787           | —               | —       |
| WebSocket (chat)                 | ✅ 2 estágios| ✅             | OC tem streaming real | M  |
| Hot reload (4 modos)             | ✅       | ❌ reinicia total | Real            | M       |
| Streaming de respostas           | ✅       | ❌ bloqueante     | Real            | L       |
| Auth Bearer token                | ✅       | ✅                | —               | —       |
| Device pairing (WebCrypto)       | ✅       | ❌                | Segurança       | M       |
| Tailscale auth                   | ✅       | ❌                | Diferencial     | M       |
| Dashboard: Chat completo         | ✅       | ✅ básico         | Faltam abort/inject | S   |
| Dashboard: Cron panel            | ✅       | ❌                | Real            | M       |
| Dashboard: Channels panel        | ✅ QR    | ❌                | Real            | M       |
| Dashboard: Sessions completo     | ✅       | ✅ básico         | —               | —       |
| Dashboard: Config schema-driven  | ✅       | ❌ básico         | Real            | M       |
| Dashboard: Debug/RPC manual      | ✅       | ❌                | Real            | S       |
| Dashboard: Exec approval         | ✅       | ❌                | Segurança       | M       |
| Dashboard: Update system         | ✅       | ❌                | Menor           | S       |
| Telemetria / cost tracking       | ✅       | ✅                | —               | —       |
| Log streaming filtráveis         | ✅       | ✅ /ws/logs       | —               | —       |
| Multi-agent routing              | ✅       | ✅ menção+tag     | OC tem workspace isolation | M |
| Telegram (nativo)                | ✅       | ⚠️ subprocess    | Frágil          | L       |
| WhatsApp (QR code, nativo)       | ✅       | ⚠️ subprocess    | Frágil          | L       |
| Discord (nativo)                 | ✅       | ⚠️ template only | Real            | M       |
| Slack (nativo)                   | ✅       | ⚠️ template only | Real            | M       |
| iMessage / Mattermost            | ✅       | ❌                | N/A por ora     | —       |
| Teams                            | ❌       | ⚠️ template      | —               | —       |
| Menção por grupo                 | ✅       | ✅ @nome no texto | Menor           | S       |
| Audio/media (STT/TTS)            | ✅       | ✅ Whisper        | —               | —       |
| Skills marketplace               | ✅ 5700+ | ⚠️ 37 (14 stable)| Enorme          | L       |
| Skills: install/publish          | ✅       | ✅ ZIP+SHA256     | —               | —       |
| Skills: auto-update              | ✅       | ✅ trust+rollback | —               | —       |
| Memória persistente              | ✅       | ✅ MD+SQLite      | —               | —       |
| Busca semântica real (embeddings)| n/d      | ❌ keyword scoring| Real            | L       |
| Learning loop com retry          | n/d      | ✅                | Diferencial +   | —       |
| Ollama offline fallback          | ❌       | ✅                | Diferencial +   | —       |
| MCP client (add/list/remove)     | ❌       | ✅                | Diferencial +   | —       |
| MCP server (tools/list+call)     | ❌       | ✅                | Diferencial +   | —       |
| Chamada real a API de LLM        | ✅       | ❌ **STUB**       | **CRÍTICO**     | M       |
| Backup/restore automático        | n/d      | ❌ (ROADMAP P0)   | Real            | S       |
| Secret scanning CI               | n/d      | ✅ secret-scan.yml| —               | —       |
| Unit/integration tests           | n/d      | ✅ 17 arquivos    | —               | —       |
| Runbook / alertas auto           | n/d      | ❌ (ROADMAP)      | Real            | S       |

---

## D) TOP 10 GAPS CRÍTICOS (por impacto)

### GAP 1 — `run_remote_provider` é STUB (BLOQUEANTE)
**Arquivo:** `clawlite/runtime/offline.py:63-66`
```python
def run_remote_provider(prompt: str, model: str, token: str) -> str:
    if not token:
        raise ProviderExecutionError("token ausente para provedor remoto")
    return f"[{model}] {prompt}"   # ← STUB — não chama API real
```
Toda a cadeia `run_task_with_learning → run_with_offline_fallback → run_remote_provider`
nunca chama a API da Anthropic/OpenAI/OpenRouter. O agente não opera de verdade.
**Prioridade: MÁXIMA. Deve ser o primeiro fix.**

### GAP 2 — Integração de canais via `shell=True` + command_template
**Arquivo:** `clawlite/runtime/multiagent.py:513`
```python
proc = subprocess.run(command, shell=True, capture_output=True, text=True)
```
Canais não usam SDK Python nativo. Polling de mensagens no Telegram/WhatsApp/Discord
não existe em código Python — só templates de config e subprocess. Sem reconexão
automática, sem rate-limit nativo, risco de command injection se `{text}` não for sanitizado.

### GAP 3 — Dashboard incompleto (cron, channels, streaming, approval)
- Sem cron panel (criação/edição/histórico de jobs, webhooks)
- Sem channel status panel com QR code login
- Sem streaming de respostas (SSE/WebSocket chunks)
- Sem exec approval/policy de segurança
- Sem schema-driven config editor com validação

### GAP 4 — Skills: 23/37 em "dev", hub manifest pode estar vazio em produção
`DEFAULT_INDEX_URL` aponta para `manifest.local.json` no repositório principal.
Em produção, esse arquivo pode não conter os 37 pacotes empacotados com SHA256.
Ecossistema: 37 vs 5700+ do OpenClaw é um gap de anos.

### GAP 5 — "Semantic search" sem embeddings reais
**Arquivo:** `clawlite/runtime/session_memory.py:87-113`
```python
score = sum(1 for t in tokens if t in low)  # keyword matching puro
```
Sem sentence-transformers, FAISS, ou vetores. Compromete qualidade de recuperação de contexto.

### GAP 6 — `shell=True` sem sanitização → command injection
Worker executa `subprocess.run(command, shell=True)` onde `command = template.format(**payload)`.
Se `payload["text"]` contém `` ` ``, `;` ou `&&`, há risco real de command injection
via mensagem de canal.

### GAP 7 — Sem backup/restore automático dos 3 DBs críticos
`~/.clawlite/multiagent.db`, `learning.db`, `config.json` não têm backup automático.
Item P0 do ROADMAP não implementado. Perda total de dados em falha de disco.

### GAP 8 — MCP templates requerem Node.js/npx (contradição)
**Arquivo:** `clawlite/mcp.py:16-26`
```python
"filesystem": {"url": "npx -y @modelcontextprotocol/server-filesystem ~/"},
"github":     {"url": "npx -y @modelcontextprotocol/server-github"},
```
O projeto se posiciona como "sem Node.js" mas os únicos templates MCP instaláveis exigem `npx`.

### GAP 9 — Sem hot-reload / sem daemon mode
Gateway requer restart completo do uvicorn para toda mudança de config.
OpenClaw tem 4 modos de reload (hot/restart/hybrid/off).
Sem `--install-daemon`, o processo morre com o terminal.

### GAP 10 — Token em JSON plain, sem rotação, sem device pairing
Token do gateway armazenado em `~/.clawlite/config.json` sem criptografia.
Sem mecanismo de rotação via CLI. Sem device pairing para acessos remotos.

---

## E) PLANO DE EXECUÇÃO EM 3 FASES

### FASE 1 — Fundação Operacional (7 dias)
**Objetivo: Fazer o agente funcionar de verdade em produção**

| # | Entregável | Risco | Critério de aceite |
|---|------------|-------|-------------------|
| 1 | Implementar chamada real à API LLM em `run_remote_provider` | Alto | `clawlite run "oi"` retorna resposta real da API |
| 2 | Fix security: Substituir `shell=True` por lista de args + sanitizar command_template | Alto | Mensagem com `;rm -rf` não executa comando |
| 3 | Implementar polling nativo Telegram (httpx ou python-telegram-bot) | Médio | Bot responde < 3s sem subprocess intermediário |
| 4 | CI completo: pytest + type-check + secret_scan + smoke test | Baixo | Badge verde no README, falha em token exposto |
| 5 | Backup/restore automático dos 3 SQLite DBs + config.json | Baixo | `clawlite backup create` gera `.tar.gz` recuperável |
| 6 | Token rotation via CLI + aviso de token em plain text | Baixo | `clawlite gateway rotate-token` gera novo token |

### FASE 2 — Paridade de Dashboard (14 dias)
**Objetivo: Fechar gaps funcionais da UI**

| # | Entregável | Risco | Critério de aceite |
|---|------------|-------|-------------------|
| 7  | Cron panel completo na UI (create/edit/run/enable/disable/history/webhook) | Médio | Usuário cria job recorrente pela UI sem editar JSON |
| 8  | Channels panel com status real de cada canal + reconexão | Médio | Dashboard mostra "Telegram: online" e botão Reconnect |
| 9  | Streaming de respostas via WebSocket chunks | Alto | Resposta aparece progressivamente no chat |
| 10 | Config editor avançado (schema-driven com validação de campo) | Baixo | UI valida e rejeita config inválida antes de salvar |
| 11 | Abort de execução + injection de nota do assistente | Baixo | Botão "Stop" na UI interrompe task em andamento |
| 12 | Hot-reload de config (SIGHUP handler) | Médio | `clawlite gateway reload` aplica config sem derrubar conexões |

### FASE 3 — Ecossistema e Qualidade Prod (30 dias)
**Objetivo: Fechar gaps de ecossistema e hardening**

| # | Entregável | Risco | Critério de aceite |
|---|------------|-------|-------------------|
| 13 | Integração nativa Discord e Slack (discord.py + slack_bolt) | Alto | Bot Discord responde sem subprocess |
| 14 | 10+ skills stable empacotadas no hub manifest com SHA256 real | Médio | `clawlite skill install github` baixa, valida e executa |
| 15 | MCP templates sem npx (uvx ou python -m) | Baixo | `clawlite mcp install filesystem` sem Node.js |
| 16 | Semantic search real (sentence-transformers + FAISS leve) | Alto | Busca retorna resultado semanticamente relevante sem keyword exact |
| 17 | Exec approval policy (allowlist de comandos sensíveis) | Médio | `shell_exec rm -rf /tmp/test` requer aprovação do usuário |
| 18 | Observabilidade: alertas no Telegram (gateway down, error rate > 10%) | Baixo | Alerta em < 60s após gateway cair |
| 19 | Daemon mode (systemd unit gerado pelo installer) | Baixo | Gateway sobrevive a reboot sem intervenção manual |
| 20 | Runbook de incidentes (gateway down, DB lock, channel auth) | Baixo | `docs/RUNBOOK.md` com passos reproduzíveis |

---

## F) DICAS TÉCNICAS DETALHADAS PARA CADA GAP

### DICA 1 — Implementar `run_remote_provider` de verdade

**O problema:** O código atual é um stub que nunca chama a API real.

**Solução com httpx (sem SDK proprietário, mais portável):**
```python
# clawlite/runtime/offline.py — substituir run_remote_provider

import httpx
from typing import Any

PROVIDER_CONFIGS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "models_prefix": "",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "models_prefix": "",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "models_prefix": "",
    },
}

def run_remote_provider(prompt: str, model: str, token: str, cfg: dict[str, Any] | None = None) -> str:
    provider = provider_from_model(model)
    model_name = model.split("/", 1)[1] if "/" in model else model

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if provider == "anthropic":
        headers = {
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["content"][0]["text"]

    elif provider in ("openai", "openrouter"):
        base = PROVIDER_CONFIGS.get(provider, {}).get("base_url", "https://api.openai.com/v1")
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{base}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    else:
        raise ProviderExecutionError(f"Provider não suportado: {provider}")
```

**Adicionar ao pyproject.toml:**
```toml
dependencies = ["fastapi>=0.112", "uvicorn>=0.30", "questionary>=2.0.1", "rich>=13.7.1", "httpx>=0.27"]
```

---

### DICA 2 — Corrigir `shell=True` (security fix)

**O problema:** `subprocess.run(command, shell=True)` com template não sanitizado.

**Solução:**
```python
# clawlite/runtime/multiagent.py — substituir _render_command e worker_loop

import shlex

def _render_command_args(template: str, payload: dict[str, Any]) -> list[str]:
    """Retorna lista de args segura, sem shell=True."""
    merged = {
        "text": shlex.quote(str(payload.get("text", ""))),
        "label": shlex.quote(str(payload.get("label", ""))),
        "chat_id": shlex.quote(str(payload.get("chat_id", ""))),
        "channel": shlex.quote(str(payload.get("channel", "telegram"))),
    }
    try:
        rendered = template.format(**merged)
    except KeyError as exc:
        raise ValueError(f"Template inválido: {exc}") from exc
    return shlex.split(rendered)


# No worker_loop, trocar:
# proc = subprocess.run(command, shell=True, ...)
# por:
args = _render_command_args(worker.command_template, payload)
proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
```

---

### DICA 3 — Polling nativo Telegram (sem subprocess)

**Instalar:**
```bash
pip install python-telegram-bot>=20.0
```

**Implementação mínima funcional:**
```python
# clawlite/runtime/telegram_bot.py

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from clawlite.core.agent import run_task_with_learning

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    chat_id = update.effective_chat.id
    # Integrar com select_agent_for_message e multiagent queue
    reply = run_task_with_learning(text)
    await update.message.reply_text(reply)

def start_telegram_bot(token: str) -> None:
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
```

**Integrar com o gateway (background thread):**
```python
# Em gateway/server.py, ao iniciar:
import threading
from clawlite.runtime.telegram_bot import start_telegram_bot

cfg = load_config()
tg_cfg = cfg.get("channels", {}).get("telegram", {})
if tg_cfg.get("enabled") and tg_cfg.get("token"):
    t = threading.Thread(target=start_telegram_bot, args=(tg_cfg["token"],), daemon=True)
    t.start()
```

---

### DICA 4 — Streaming de respostas via WebSocket

**Problema:** `run_task_with_meta` é síncrono e bloqueante.

**Solução com Server-Sent Events (mais simples) ou WebSocket chunks:**

```python
# Para Anthropic com streaming:
import anthropic

async def stream_task(prompt: str, websocket: WebSocket, session_id: str) -> str:
    client = anthropic.Anthropic(api_key=token)
    full_text = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            full_text += chunk
            await websocket.send_json({
                "type": "chat_chunk",
                "session_id": session_id,
                "delta": chunk,
            })
    # Envia o sinal de finalização
    await websocket.send_json({"type": "chat_done", "session_id": session_id})
    return full_text
```

**No ws_chat endpoint, substituir `_handle_chat_message` por `stream_task`.**

---

### DICA 5 — Hot-reload sem reiniciar gateway

**Adicionar handler de SIGHUP:**
```python
# Em gateway/server.py — adicionar ao run_gateway()

import signal
from clawlite.config.settings import load_config

def _handle_sighup(signum, frame):
    """Recarrega config sem derrubar conexões ativas."""
    global _cached_config
    _cached_config = load_config()
    _log("gateway.config_reloaded", data={"trigger": "SIGHUP"})

def run_gateway(host=None, port=None):
    signal.signal(signal.SIGHUP, _handle_sighup)
    # ... resto do código
```

**CLI:**
```bash
# clawlite gateway reload
kill -HUP $(cat ~/.clawlite/gateway.pid)
```

**Salvar PID ao iniciar:**
```python
# Em run_gateway(), após bind:
pid_file = CONFIG_DIR / "gateway.pid"
pid_file.write_text(str(os.getpid()), encoding="utf-8")
```

---

### DICA 6 — Backup automático dos DBs críticos

```python
# clawlite/runtime/backup.py

import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

BACKUP_DIR = Path.home() / ".clawlite" / "backups"
SOURCES = [
    Path.home() / ".clawlite" / "multiagent.db",
    Path.home() / ".clawlite" / "learning.db",
    Path.home() / ".clawlite" / "memory.db",
    Path.home() / ".clawlite" / "config.json",
    Path.home() / ".clawlite" / "mcp.json",
    Path.home() / ".clawlite" / "workspace",
]

def create_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive = BACKUP_DIR / f"clawlite_backup_{ts}.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        for src in SOURCES:
            if src.exists():
                tar.add(src, arcname=src.name)

    # Manter apenas os últimos 7 backups
    all_backups = sorted(BACKUP_DIR.glob("clawlite_backup_*.tar.gz"))
    for old in all_backups[:-7]:
        old.unlink(missing_ok=True)

    return archive

def restore_backup(archive_path: Path) -> None:
    target = Path.home() / ".clawlite"
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(target)
```

**Agendar via cron interno (adicionar ao `clawlite start`):**
```python
from clawlite.runtime.backup import create_backup
# Backup diário às 03:00
schedule.every().day.at("03:00").do(create_backup)
```

---

### DICA 7 — Semantic search real com embeddings leves

**Instalar (leve, funciona no Termux):**
```bash
pip install sentence-transformers faiss-cpu
# No Termux (sem GPU):
pip install sentence-transformers  # FAISS é opcional, sqlite-vec é mais leve
```

**Implementação com sqlite-vec (mais portável que FAISS):**
```bash
pip install sqlite-vec
```

```python
# clawlite/runtime/vector_memory.py

import json
import sqlite3
from pathlib import Path
import sqlite_vec
from sentence_transformers import SentenceTransformer

DB_PATH = Path.home() / ".clawlite" / "vector_memory.db"
MODEL_NAME = "all-MiniLM-L6-v2"  # 80MB, roda no Termux

_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_vss
        USING vec0(embedding FLOAT[384])
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_texts (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL,
            source TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    return conn

def add_memory(text: str, source: str = "") -> None:
    model = _get_model()
    emb = model.encode(text).tolist()
    conn = _conn()
    with conn:
        cur = conn.execute("INSERT INTO memory_texts (text, source) VALUES (?, ?)", (text, source))
        rowid = cur.lastrowid
        conn.execute("INSERT INTO memory_vss (rowid, embedding) VALUES (?, vec_f32(?))",
                     (rowid, json.dumps(emb)))

def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    model = _get_model()
    emb = model.encode(query).tolist()
    conn = _conn()
    rows = conn.execute("""
        SELECT mt.text, mt.source, vs.distance
        FROM memory_vss vs
        JOIN memory_texts mt ON mt.id = vs.rowid
        WHERE vs.embedding MATCH vec_f32(?)
        ORDER BY vs.distance
        LIMIT ?
    """, (json.dumps(emb), top_k)).fetchall()
    return [{"text": r[0], "source": r[1], "score": 1 - r[2]} for r in rows]
```

---

### DICA 8 — MCP templates sem Node.js

**Substituir em `clawlite/mcp.py`:**
```python
KNOWN_SERVER_TEMPLATES: dict[str, dict[str, str]] = {
    # Python-native (sem npx)
    "filesystem": {
        "name": "filesystem",
        "url": "uvx mcp-server-filesystem ~/",
        "description": "Servidor MCP para acesso ao filesystem local (via uvx, sem Node.js).",
    },
    "github": {
        "name": "github",
        "url": "uvx mcp-server-github",
        "description": "Servidor MCP para GitHub (via uvx, exige GITHUB_TOKEN).",
    },
    "sqlite": {
        "name": "sqlite",
        "url": "uvx mcp-server-sqlite --db-path ~/.clawlite/memory.db",
        "description": "Servidor MCP para SQLite local (memória do ClawLite).",
    },
    "fetch": {
        "name": "fetch",
        "url": "uvx mcp-server-fetch",
        "description": "Servidor MCP para fetch de URLs (web scraping simples).",
    },
}
```

**Pré-requisito (instalar uvx):**
```bash
pip install uv  # uv inclui uvx
```

---

### DICA 9 — Daemon mode com systemd

**Gerar unit file via CLI:**
```bash
clawlite install-daemon  # novo comando
```

**Implementação:**
```python
# clawlite/runtime/daemon.py

import os
from pathlib import Path

UNIT_TEMPLATE = """[Unit]
Description=ClawLite Gateway
After=network.target

[Service]
Type=simple
User={user}
ExecStart={clawlite_bin} start --host 0.0.0.0 --port {port}
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

def install_systemd_daemon(port: int = 8787) -> Path:
    import subprocess
    import shutil
    clawlite_bin = shutil.which("clawlite") or f"{Path.home()}/.local/bin/clawlite"
    unit_content = UNIT_TEMPLATE.format(
        user=os.getlogin(),
        clawlite_bin=clawlite_bin,
        port=port,
    )
    unit_path = Path(f"{Path.home()}/.config/systemd/user/clawlite.service")
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(unit_content, encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", "--now", "clawlite"])
    return unit_path
```

---

### DICA 10 — Cron panel completo no Dashboard

**Expor APIs necessárias no gateway:**
```python
# Adicionar em gateway/server.py

from clawlite.runtime.conversation_cron import (
    add_cron_job, list_cron_jobs, remove_cron_job,
    enable_cron_job, disable_cron_job, run_cron_job_now
)

@app.get("/api/cron")
def api_cron_list(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    return JSONResponse({"ok": True, "jobs": list_cron_jobs()})

@app.post("/api/cron")
def api_cron_create(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    job_id = add_cron_job(
        channel=str(payload.get("channel", "system")),
        chat_id=str(payload.get("chat_id", "local")),
        thread_id=str(payload.get("thread_id", "")),
        label=str(payload.get("label", "cron")),
        name=str(payload.get("name", "")),
        text=str(payload.get("text", "")),
        interval_seconds=int(payload.get("interval_seconds", 3600)),
        enabled=bool(payload.get("enabled", True)),
    )
    return JSONResponse({"ok": True, "job_id": job_id})

@app.post("/api/cron/{job_id}/run")
def api_cron_run(job_id: int, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    run_cron_job_now(job_id)
    return JSONResponse({"ok": True, "job_id": job_id})

@app.delete("/api/cron/{job_id}")
def api_cron_delete(job_id: int, authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    remove_cron_job(job_id)
    return JSONResponse({"ok": True, "removed": job_id})
```

---

## G) MELHORIAS ADICIONAIS RECOMENDADAS

### Melhoria 1 — Rate limiting por canal no gateway
```python
# clawlite/runtime/resilience.py já tem RateLimiter — usá-lo no gateway:
from clawlite.runtime.resilience import RateLimiter

_channel_limiters: dict[str, RateLimiter] = {}

def _get_limiter(channel: str) -> RateLimiter:
    if channel not in _channel_limiters:
        _channel_limiters[channel] = RateLimiter(rate_per_sec=2.0, burst=10)
    return _channel_limiters[channel]
```

### Melhoria 2 — Health check profundo (`/health/deep`)
```python
@app.get("/health/deep")
async def health_deep() -> JSONResponse:
    checks = {
        "gateway": True,
        "sqlite_multiagent": _check_db("multiagent.db"),
        "sqlite_learning": _check_db("learning.db"),
        "ollama": await _check_ollama(),
        "telegram": _check_telegram_token(),
    }
    ok = all(checks.values())
    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)
```

### Melhoria 3 — Token rotation automática a cada 30 dias
```python
# Em run_gateway(), verificar idade do token:
from datetime import datetime, timezone, timedelta

def _rotate_token_if_old(cfg: dict) -> None:
    gateway_cfg = cfg.get("gateway", {})
    created_at = gateway_cfg.get("token_created_at")
    if created_at:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(created_at)
        if age > timedelta(days=30):
            new_token = secrets.token_urlsafe(24)
            gateway_cfg["token"] = new_token
            gateway_cfg["token_created_at"] = datetime.now(timezone.utc).isoformat()
            save_config(cfg)
            _log("gateway.token_rotated", level="warn", data={"reason": "age>30d"})
```

### Melhoria 4 — Cache de respostas para prompts idênticos
```python
# clawlite/runtime/response_cache.py
import hashlib, json, sqlite3
from pathlib import Path

CACHE_DB = Path.home() / ".clawlite" / "response_cache.db"

def get_cached(prompt: str, model: str, ttl_seconds: int = 3600) -> str | None:
    key = hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()
    with sqlite3.connect(str(CACHE_DB)) as conn:
        row = conn.execute(
            "SELECT response FROM cache WHERE key=? AND created_at > datetime('now', ?)",
            (key, f"-{ttl_seconds} seconds")
        ).fetchone()
    return row[0] if row else None

def set_cached(prompt: str, model: str, response: str) -> None:
    key = hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()
    with sqlite3.connect(str(CACHE_DB)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, response TEXT, created_at TEXT DEFAULT (datetime('now')))")
        conn.execute("INSERT OR REPLACE INTO cache (key, response) VALUES (?, ?)", (key, response))
```

### Melhoria 5 — Observabilidade: métricas Prometheus
```python
# pip install prometheus-client
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

task_counter = Counter("clawlite_tasks_total", "Total de tasks", ["result", "model", "skill"])
task_duration = Histogram("clawlite_task_duration_seconds", "Duração das tasks")

@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### Melhoria 6 — Multi-model routing inteligente (cost-aware)
```python
# Selecionar modelo mais barato para tasks simples:
def select_model_for_task(prompt: str, cfg: dict) -> str:
    word_count = len(prompt.split())
    if word_count < 50 and not any(kw in prompt.lower() for kw in ["código", "analise", "compare"]):
        return "openai/gpt-4o-mini"  # Mais barato para tasks simples
    return cfg.get("model", "claude-sonnet-4-6")  # Padrão para tasks complexas
```

### Melhoria 7 — Dashboard: indicador de custo em tempo real
Adicionar ao `dashboard.html` um contador de custo acumulado por sessão,
atualizado via WebSocket a cada resposta. Mostra custo estimado em USD ao lado
de cada mensagem no chat.

### Melhoria 8 — Workspace isolado por agente
```python
# Cada agente tem seu próprio diretório de memória:
def agent_workspace(agent_name: str) -> Path:
    base = Path.home() / ".clawlite" / "agents" / agent_name
    base.mkdir(parents=True, exist_ok=True)
    return base
```

### Melhoria 9 — `clawlite doctor --fix` automático
```python
# Detectar e corrigir automaticamente problemas comuns:
def doctor_fix(cfg: dict) -> list[str]:
    fixes = []
    if not cfg.get("gateway", {}).get("token"):
        cfg.setdefault("gateway", {})["token"] = secrets.token_urlsafe(24)
        fixes.append("Token do gateway gerado automaticamente")
    if not Path.home().joinpath(".clawlite", "workspace").exists():
        init_workspace()
        fixes.append("Workspace inicializado")
    # ... etc
    return fixes
```

### Melhoria 10 — Plugin system para canais de terceiros
```python
# Permitir instalar canais como skills:
# clawlite channel install whatsapp-baileys
# clawlite channel install iMessage
```

---

## H) INCONSISTÊNCIAS DETECTADAS ENTRE README E CÓDIGO

| Claim no README | Realidade no código | Severidade |
|-----------------|---------------------|-----------|
| "Learning system em produção ✅" | `run_remote_provider` é stub — agente não opera | **Alta** |
| "Multi-agente multi-canal ✅" | Canais via subprocess/command_template, sem bot nativo | **Média** |
| "Busca semântica" | Keyword matching simples (score = count de tokens presentes) | **Média** |
| "37 Skills" | 37 declaradas, mas hub manifest.local.json pode estar sem pacotes | **Média** |
| "MCP: sem Node.js" | Templates MCP usam `npx` (Node.js obrigatório) | **Baixa** |
| "OpenAI-compatible API" | Não há endpoint `/v1/chat/completions` no gateway | **Baixa** |

---

## I) VEREDITO FINAL

```
┌─────────────────────────────────────────────────────────────────┐
│  VEREDITO:  "AINDA DISTANTE"                                    │
│  Paridade estimada: ~35–40%                                     │
│                                                                 │
│  Não é "quase lá". Há um gap funcional crítico (stub de LLM)   │
│  que torna o agente inoperante em produção sem correção manual. │
│  A arquitetura é sólida e o potencial é real, mas a distância  │
│  para o nível OpenClaw ainda é de 3–4 meses de trabalho        │
│  focado, não 7 dias.                                            │
└─────────────────────────────────────────────────────────────────┘
```

### Pontos fortes reais (evidenciados em código)
- Marketplace com segurança real (SHA256, rollback, path traversal guard) — nível produção
- Learning loop com WAL, retry backoff, template learning — arquitetura correta
- MCP server JSON-RPC 2.0 funcional exposto via gateway — único entre alternativas analisadas
- installer.sh com auto-detecção Termux — melhor que OpenClaw nesse nicho
- 17 arquivos de teste (1.731 linhas) — comprometimento com qualidade
- secret-scan.yml no CI — boa prática de segurança

### O que define "ainda distante"
- `run_remote_provider` é stub — o agente não opera sem intervenção no código
- Integração de canais via subprocess/shell=True — não é produção-ready
- Dashboard sem cron panel, channel panel, streaming, device pairing
- Ecossistema de skills 154x menor (37 vs 5700+)
- Sem daemon, sem hot-reload, sem backup automático

### Roadmap de paridade realista
- **+7 dias (fix stub + security)**: Paridade sobe para ~50%
- **+14 dias (dashboard)**: Paridade sobe para ~60%
- **+30 dias (canais nativos + skills)**: Paridade sobe para ~70%
- **+90 dias (ecossistema + observabilidade)**: Paridade sobe para ~85%

**O projeto tem fundação técnica honesta e código de qualidade.**
**Com foco no stub do LLM como prioridade máxima, a trajetória é promissora.**

---

*Gerado em: 2026-02-27*
*Código-fonte auditado: /root/projetos/ClawLite/ (commit main, v0.4.1)*
*Referência OpenClaw: https://docs.openclaw.ai (docs públicas, fev/2026)*
