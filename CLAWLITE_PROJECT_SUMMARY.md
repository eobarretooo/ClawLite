# ClawLite: Projeto de Paridade com OpenClaw 🦊

Este documento serve como o registro histórico e planejamento consolidado do projeto **ClawLite**, uma re-implementação nativa em Python do framework *OpenClaw* (originalmente em TypeScript/Node.js).

## 1. Visão Original e Objetivo
O objetivo fundamental do projeto foi analisar a arquitetura complexa do **OpenClaw** (que usa Docker, CDP pesado, e um monólito de gateway gigantesco em TS) e extrair sua essência para construir o **ClawLite**: um agente leve, local-first, modular, totalmente em Python 3.10+, seguro (sem chamadas `shell=True` cegas), focado no idioma PT-BR, com mascote próprio (uma Raposa 🦊 ao invés de Lagosta 🦞).

### Tabela de Paridade Original:
| Feature | OpenClaw | ClawLite (Nossa Meta) |
|---|---|---|
| **Linguagem** | TypeScript/Node.js | Python 3.10+ |
| **Instalação** | `npm` e binários globais | `pip` e gerenciadores Python (`uv`) |
| **Configuração** | `~/.openclaw/openclaw.json` | `~/.clawlite/config.json` |
| **Integrações (Canais)** | ~22 conectores pesados | Foco modular nos Top 8 (Telegram, WP, etc) |
| **Segurança** | Flexível/Dockerizado | Restrito no Host (Sem `shell=True` solto) |

---

## 2. O Que Foi Construído Até Agora (Sprints 1 a 3)

### ✅ Sprint 1: Gateway Refactor & Segurança P0
O código base do ClawLite herdou um Gateway monolítico e dezenas de Skills perigosas do protótipo inicial.
*   **Resultados:**
    *   **Refatoração do Gateway (`gateway/`):** Desmembramos o arquivo de `1478` linhas em rotas granulares (`routes/agents.py`, `skills.py`, `cron.py`, `websockets.py`, etc).
    *   **Saneamento de Skills:** Removemos o flag `shell=True` de mais de 15 tools do sistema. Implementamos parses seguros via `shlex` para comandos de terminal (`exec_cmd`).
    *   **Dashboard Local:** Garantimos que a fundação de API continuasse se comunicando de forma transparente com a UI de Dashboard do usuário rodando React.

### ✅ Sprint 2: Canais de Comunicação Reais
Expandimos o ClawLite para além de uma mera API local, conectando ele com redes abertas em tempo real.
*   **Resultados:**
    *   **Telegram Bridge:** Criamos o `channels/telegram.py` usando `python-telegram-bot` (`v21+`). O agente consegue ouvir mensagens, manter threads contínuas via Message IDs e disparar o runtime nativamente com respostas em markdown formatado no Telegram.
    *   **Session State isolation:** O backend agora entende que o Telegram e o Dashboard Web são `channels` diferentes, guardando o histórico e a memória (Long-term) adequadamente por usuário/ID de sessão.

### ✅ Sprint 3: Agent Runtime Avançado (Coração do LLM)
Esta foi a repaginação do cérebro matemático para interações avançadas de tempo-real e execução multi-passos.
*   **Resultados:**
    *   **Token Streaming:** Implementamos SSE (Server-Sent Events) conectando aos WebSockets nativos (`/ws/chat`). Ao invés de esperar 10 segundos por uma resposta longa, o Gateway agora flui pedaço-por-pedaço (`yield chunks`) pro cliente.
    *   **Tool Calling Nativo (ReAct Loop):** Ensinamos a LLM a retornar JSON estrito (ex: `{"name": "exec_cmd", "arguments": {"command": "ls"}}`) ao invés de jogar Python arbitrário. O loop iterativo (`run_task_with_learning`) pega essa tool, executa localmente a função segura e devolve pro LLM analisar o output.
    *   **Model Failover Tolerante:** Para garantir alta-disponibilidade, modelamos priorização em cascata. Se a (Primary) Anthropic/OpenAI der timeout ou falhar, o ClawLite migra a requisição automaticamente para modelos secundários em nuvem (Groq/OpenRouter) antes do *Fallback Local de Emergência* pro Ollama.

---

## 3. Em Andamento/Próximos Passos (Sprint 4 em Diante)

### 🟡 Sprint 4: Browser, Voice e TUI (Fundação Iniciada)
Dar ao ClawLite "mãos web", "ouvidos/voz" e um painel Hacker.
*   **Browser Control (Playwright):** Já criamos um `BrowserManager` local em Python que tira uma "foto de texto" da página renderizada (JSON da DOM) com IDs estáticos (`claw-id`) para o LLM clicar e preencher formulários com extrema facilidade, sem a complexidade pesada do CDP/Chrome Puppeteer do OpenClaw.
*   **Voice Pipeline:** Planejado o suporte a APIs de fala de baixo custo online (`OpenAI Whisper/TTS`) e fallbacks de processamento de áudio 100% local (`whisper.cpp`).
*   **TUI:** Usaremos a biblioteca `textual` para oferecer log management visual direto no CMD/Powershell de quem não usa a interface gráfica Web.

### 🔜 Sprint 5: Dashboard Nativo Premium e Telemetria
Evoluir a UI para gerenciar cron jobs, verificar custos mensais das APIs, instalar novos skills/extensões em um clique, etc.

### 🔜 Sprint 6: Instalador Simplificado e Plugin SDK
Permitir que usuários finais testem via simples `pip install clawlite && clawlite start`. Fornecer classe `Plugin` em Python para customizações.

---
🦊 *Relatório Gerado Automaticamente pela IA de Planejamento do ClawLite.*
