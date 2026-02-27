# ClawLite — MEMORY

## Missão
Construir um assistente open source, portátil e poderoso para Linux e Termux, com operação local/online, multi-agente e ecossistema de skills comunitárias.

## Dono do projeto
- **Nome**: Renan (username: eobarretooo)
- **Comunicação**: direto, objetivo, zero fluff
- **Autonomia total**: sem confirmações, só avisa em blocker/decisão de produto

## Repositórios
- **ClawLite (público)**: github.com/eobarretooo/ClawLite — branch `main`
- **clawlite-site (privado)**: github.com/eobarretooo/clawlite-site — Astro, deploy GitHub Pages
- **Perfil GitHub**: github.com/eobarretooo/eobarretooo — README profissional + snake
- **VeloRota**: local em `/root/projetos/velorota` — **PAUSADO** até ClawLite concluído

## Estado atual — v0.4.0 (tag publicada)

### ✅ Concluído
1. **CLI base**: `clawlite doctor/run/memory/configure/onboarding/status`
2. **Memória SQLite** + tools locais (read/write/exec)
3. **Gateway WebSocket** com token auth + dashboard v2 (chat realtime, telemetria, logs filtráveis)
4. **OAuth** para 5 provedores (`clawlite auth login/status/logout`)
5. **Configure interativo OpenClaw-style** — setas, checkboxes, PT-BR, preview antes de salvar
   - Seções: Model, Channels, Skills, Hooks, Gateway, Web Tools, Language, Security
6. **Onboarding** wizard guiado com barra de progresso + resumo final
7. **Doctor expandido**: python, git, curl, sqlite, conectividade, config obrigatória
8. **Status command**: mostra gateway, workers, cron, reddit monitor
9. **37 skills** registradas no registry
10. **Marketplace** de skills seguro (install/update/publish com allowlist+checksum+zip)
11. **Multi-agente persistente Telegram** (MVP): SQLite workers, label routing, CLI agents, auto-recover
12. **Offline fallback Ollama** + notificações inteligentes (prioridade+dedupe)
13. **Cron jobs por conversa** (SQLite, CLI list/add/remove/run) + modo bateria com throttling
14. **Reddit integração**: OAuth, post milestone em 4 subreddits, monitor menções hora a hora com sugestão no Telegram
15. **Docs i18n**: PT-BR default + EN, Docusaurus + GitHub Actions, live em eobarretooo.github.io/ClawLite/
16. **README profissional** com badges + mascote (ASCII cat + fox SVG)
17. **Hardening**: IndentationError fixes, PT-BR padronizado, +5 integration tests, troubleshooting docs
18. **25 testes passando** (pytest)
19. **Site oficial ClawLite** (Astro, dark mode, responsivo, deploy GitHub Pages) — repo privado
20. **Perfil GitHub** com banner animado, stats, streak, snake de commits

### Commits importantes (últimos)
- `f8349e8` — release notes v0.4.0
- `91a5ed4` — integração Reddit completa
- `b040a2a` — configurador interativo OpenClaw-style
- `c2c0cdf` — clawlite status e doctor expandido
- `828dcc2` — testes configure/onboarding/status/doctor + README
- `25eba6d` — perfil GitHub (nome corrigido para Renan)
- `e22bf41` — snake de commits no perfil
- `b70d33b` — site oficial ClawLite (Astro)

### Threads publicados
- Release v0.4.0: `18040400231539476`
- Reddit + learning: `18078820193460413`

## Roadmap — O que falta

### 🔴 Próximos (prioridade)
1. **Agent Lightning-style continuous learning** no ClawLite
   - Task tracking, auto-retry com histórico, preference learning, prompt auto-improvement
   - `clawlite stats` command
   - Ref: https://github.com/microsoft/agent-lightning
2. **BarretoClaw self-learning** (base criada em `~/.openclaw/learning/`)
   - failures.json, corrections.json, preferences.json
   - weekly report funcional
   - Falta: integrar no loop principal de decisão, relatório automático semanal no Telegram
3. **Package release** tag + changelog formal
4. **Docs públicas consolidadas** com novos comandos
5. **Multi-agent Telegram field validation** com bot real

### 🟡 Médio prazo
6. **Skills reais** (evoluir de wrappers): ollama, cron, whisper, github, google-drive
7. **Auto-update de skills** (Issue #2)
8. **Voice** — STT/TTS no Telegram/WhatsApp (Issue #4)
9. **Skills CLI** avançado (Issue #9)
10. **Site de skills** estilo skills.sh (Issue #10)
11. **Domínio clawlite.dev** — Renan precisa registrar, eu configuro CNAME

### 🟢 Depois do ClawLite
12. **VeloRota** — retomar Session 4+: heatmap, restaurants seed, UX, push GitHub

## Contexto técnico
- **Venv**: `~/.clawlite/venv/bin/python`
- **Config**: `~/.clawlite/config.json`
- **Multi-agent DB**: `~/.clawlite/multiagent.db`
- **Marketplace**: `~/.clawlite/marketplace/installed.json`
- **Dashboard HTML**: `clawlite/gateway/dashboard.html`
- **Agent pipeline**: `clawlite/core/agent.py` → `run_task_with_meta()` → `run_with_offline_fallback()`
- **Skills registry**: `clawlite/skills/registry.py` (37 skills)
- **Reddit runtime**: `clawlite/runtime/reddit.py`
- **Reddit state**: `~/.clawlite/reddit_state.json`
- **BarretoClaw learning**: `~/.openclaw/learning/` + `~/.openclaw/workspace/scripts/barretoclaw_learning.py`
- **Threads poster**: `/root/projetos/motoboys/skills/threads-poster/scripts/post_threads.py`
- **GitHub Issues**: #1-#11 criadas (vários fechados)

## Decisões tomadas
- Astro para site (leve, rápido, SEO)
- questionary + rich para CLI interativo
- Spawn-per-task para subagentes (persistent mode indisponível)
- setuptools com `[tool.setuptools.packages.find]`
- Mascote: badge ASCII cat (terminal) + fox SVG (docs/site)
- Docs PT-BR default com EN secundário
- Site e VeloRota = repos privados; ClawLite principal = público
