<p align="center">
  <img src="assets/mascot-animated.svg" alt="ClawLite Fox Mascot" width="180" />
</p>

<h1 align="center">ClawLite</h1>

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=20&duration=3000&pause=900&center=true&vCenter=true&width=900&lines=Assistente+de+IA+open+source+para+Linux+%2B+Termux;Gateway+WebSocket+%2B+Dashboard+%2B+Skills+Marketplace;Quickstart+guiado+em+PT-BR+com+onboarding+interativo" alt="Typing SVG" />
</p>

<p align="center">
  <a href="https://github.com/eobarretooo/ClawLite/releases/tag/v0.4.1"><img src="https://img.shields.io/badge/version-v0.4.1-7c3aed?style=for-the-badge" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge" /></a>
  <a href="https://github.com/eobarretooo/ClawLite/stargazers"><img src="https://img.shields.io/github/stars/eobarretooo/ClawLite?style=for-the-badge" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Termux-supported-1f8b4c?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Idioma-PT--BR-009c3b?style=for-the-badge" />
</p>

---

## ⚡ Demo rápida

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
clawlite doctor
clawlite onboarding
clawlite start --port 8787
```

```text
┌──────────────────────────────────────────────────────────────┐
│ $ clawlite doctor                                            │
│ python: ok | sqlite: ok | runtime: ok                      │
│                                                              │
│ $ clawlite onboarding                                        │
│ [1/9] Idioma  [2/9] Modelo  [3/9] Canais ...               │
│ ✅ Configuração salva                                        │
│                                                              │
│ $ clawlite start --port 8787                                │
│ Gateway online em http://127.0.0.1:8787                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 📚 Tabela de conteúdo

- [Por que ClawLite](#-por-que-clawlite)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação](#-instalação)
- [Features](#-features)
- [Exemplos reais de uso](#-exemplos-reais-de-uso)
- [Comparação rápida](#-comparação-rápida)
- [Troubleshooting](#-troubleshooting)
- [Comunidade e suporte](#-comunidade-e-suporte)
- [Roadmap](#-roadmap)
- [Contribuindo](#-contribuindo)
- [Star History](#-star-history)
- [Licença](#-licença)

---

## 🧠 Por que ClawLite

ClawLite é um assistente de IA focado em **execução real**: CLI produtiva, gateway web, memória persistente, skills extensíveis e operação Linux/Termux-first.

- Site oficial: https://clawlite-site.vercel.app
- Docs (PT-BR): https://eobarretooo.github.io/ClawLite/
- Catálogo de skills: https://clawlite-skills-site.vercel.app

---

## ✅ Pré-requisitos

- Python **3.10+**
- Sistema **Linux** (Ubuntu/Debian/Arch etc.) ou **Termux**
- `curl` disponível no ambiente

## 🚀 Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

### Quickstart guiado (padrão)

```bash
clawlite doctor
clawlite onboarding
clawlite configure
clawlite status
clawlite start --host 0.0.0.0 --port 8787
```

> Setup manual continua disponível para usuários avançados, mas o fluxo recomendado é o wizard interativo (estilo OpenClaw).

---

## ✨ Features

- ⚙️ **Onboarding + Configure interativos** (Model, Channels, Skills, Hooks, Gateway, Security)
- 🌐 **Gateway WebSocket + Dashboard** com chat, logs e telemetria
- 🧩 **37 skills registradas** com marketplace e auto-update seguro
- 🧠 **Memória persistente** (`AGENTS/SOUL/USER/IDENTITY/MEMORY` + diário)
- 📊 **Learning stats** com métricas de sucesso/retry/performance
- 🔋 **Runtime inteligente** (offline fallback, cron por conversa, modo bateria)
- 🎙️ **Voz STT/TTS** (pipeline de áudio para canais)

---

## 💡 Exemplos reais de uso

### 1) Diagnóstico + setup
```bash
clawlite doctor
clawlite onboarding
```

### 2) Operação local com dashboard
```bash
clawlite start --port 8787
# abrir http://127.0.0.1:8787
```

Preview do runtime (terminal/status):

<p align="center">
  <img src="docs/media/clawlite-status-snapshot.png" alt="ClawLite status preview" width="820" />
</p>

### 3) Automação de skills
```bash
clawlite skill search github
clawlite skill install github
clawlite skill auto-update --apply --strict
```

### 4) Memória de sessão
```bash
clawlite memory semantic-search "preferências do usuário"
clawlite memory save-session "Resumo da sessão"
```

### 5) Exemplos de skills na prática
```bash
# GitHub: listar issues
clawlite run "use a skill github para listar issues abertas do repo"

# Whisper: transcrever áudio local
clawlite run "use whisper para transcrever ./audio/nota.ogg"
```

### 6) MCP (Model Context Protocol)
```bash
clawlite mcp add local https://example.com/mcp
clawlite mcp list
clawlite mcp search filesystem
clawlite mcp install filesystem
clawlite mcp remove local
```

Docs MCP: `docs/MCP.md`

---

## 🆚 Comparação rápida

- **ClawLite**: quickstart guiado PT-BR, Linux/Termux-first, memória persistente e runtime com fallback offline.
- **Alternativas genéricas**: muitas focam só em chat, com menos operação real (cron, dashboard integrado, pipeline de skills).

---

## 🛠️ Troubleshooting

Problemas comuns:
- Erro de dependência no ambiente Python
- Gateway não sobe na porta padrão
- Fallback offline não acionando como esperado

Guia completo: `docs/TROUBLESHOOTING.md`

---

## 💬 Comunidade e suporte

- Issues: https://github.com/eobarretooo/ClawLite/issues
- Discussões: https://github.com/eobarretooo/ClawLite/discussions
- Docs: https://eobarretooo.github.io/ClawLite/

---

## 🗺️ Roadmap

- [x] Gateway + dashboard v2
- [x] Multi-agente Telegram (MVP)
- [x] Learning hardening em produção
- [x] STT/TTS no pipeline
- [x] Auto-update de skills com trust policy + rollback
- [ ] Paridade de dashboard com OpenClaw (cron/channels/config avançada/debug)
- [ ] Voz em validação de campo contínua
- [ ] Polimento final v0.4.1.x

---

## 🤝 Contribuindo

PRs são bem-vindos! Leia `CONTRIBUTING.md`.

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=eobarretooo/ClawLite&type=Date)](https://star-history.com/#eobarretooo/ClawLite&Date)

---

## 📄 Licença

Distribuído sob licença **MIT**. Veja [LICENSE](LICENSE).
