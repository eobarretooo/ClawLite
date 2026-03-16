# ClawLite

## What This Is

ClawLite é um agente AI portátil e autônomo em Python, projetado para rodar em ambientes com restrições (Android/Termux via PRoot-Distro, aarch64). Oferece gateway FastAPI, sistema de memória multicamada, tools extensíveis, suporte a múltiplos providers LLM e canais de mensagens (Telegram, Discord, etc.), com self-evolution engine único no ecossistema.

## Core Value

Um agente AI que funciona de verdade em qualquer ambiente Python — incluindo mobile/Termux — sem dependências que compilem código nativo.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Gateway FastAPI + WebSocket com dashboard — v0.5
- ✓ Sistema de memória multicamada (episódica, semântica, working, shared) — v0.5
- ✓ 18 tools com registry e validação de schema — v0.5
- ✓ 14+ providers LLM via LiteLLM com circuit breaker — v0.5
- ✓ Canais: Telegram (completo), Discord, Slack, Email, WhatsApp — v0.5
- ✓ Cron/Heartbeat/Jobs com persistência — v0.5
- ✓ Self-Evolution Engine (Phase 7) — v0.5
- ✓ Multi-agente com SubagentManager e AutonomyWakeCoordinator — v0.5
- ✓ Skills loader com frontmatter parsing — v0.5
- ✓ Config Pydantic v1 com hot-reload e audit de tokens — v0.5

### Active

<!-- Current milestone v0.6 scope -->

- [ ] Bugs críticos corrigidos (memory leak, shell=True, setup_logging)
- [ ] MCP com stdio transport nativo
- [ ] Failover automático ao abrir circuit breaker
- [ ] Parallel tool execution no engine
- [ ] Rotação de credenciais por provider
- [ ] Health checks reais nas tools
- [ ] Rate limiting no gateway
- [ ] Thread ownership em subagentes
- [ ] Channels stub implementados (Signal/Matrix/IRC)
- [ ] Cost tracking por provider/sessão
- [ ] Cron com webhook triggers e retry policy por job

### Out of Scope

- Apps nativos iOS/Android/macOS/Windows — fora do escopo Python/Termux
- Pydantic v2 — maturin/Rust não compila no Termux
- Dependências que compilam C/Rust — quebra no ambiente Android

## Context

- **Ambiente:** PRoot-Distro em Android/Termux (aarch64) — sem llog/lunwind, não compila extensões Rust/C
- **Stack:** Python 3.12, FastAPI, Uvicorn, LiteLLM, questionary, Rich, SQLite
- **Versão atual:** v0.5.0b2
- **Paridade com referência (OpenClaw):** ~75% nos componentes comparáveis
- **Diferencial único:** Self-Evolution Engine (Phase 7) — nenhum projeto similar tem
- **Bugs conhecidos:** `_session_locks` memory leak (engine.py:324), `shell=True` em multiagent.py, `setup_logging()` no module level (engine.py:21)
- **Auditoria:** docs/AUDIT_CLAWLITE_vs_OPENCLAW_2026-02-27.md (882 linhas, ~35-40% paridade geral)

## Constraints

- **Compatibilidade:** Sem deps que compilem no Termux — always `--only-binary=:all:`
- **Pydantic:** v1.10.21 obrigatório (v2 requer maturin/Rust)
- **Python:** 3.10+ (matrix CI: 3.10, 3.12)
- **Segurança:** Nunca `shell=True` em código novo
- **Testes:** Todo teste com gateway + multiagent DEVE usar `_patch_db()` para isolar DB

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LiteLLM como abstração de providers | Suporta 100+ providers sem código custom por provider | ✓ Good |
| FastAPI + Uvicorn | Async nativo, compatível com Termux via wheels | ✓ Good |
| SQLite como backend de memória | Zero deps nativas, funciona em qualquer Python | ✓ Good |
| Pydantic v1 (não v2) | maturin/Rust não compila no Termux | ✓ Good (necessário) |
| Self-Evolution Engine desativado por default | Segurança — modificação autônoma de código requer opt-in explícito | ✓ Good |

---
*Last updated: 2026-03-16 after milestone v0.6 initialization*
