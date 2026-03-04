# ClawLite Roadmap

## P0 — Estabilidade do núcleo

- Consolidar fluxo único de execução do agente (CLI + canais + gateway)
- Expandir cobertura de testes de integração do scheduler (cron/heartbeat)
- Endurecer validação de entrada em canais e tools com I/O externo

## P1 — Autonomia operacional

- Fechar operação 24/7 em Linux com supervisão e recuperação automática
- Melhorar entrega proativa por canais com observabilidade mínima
- Fortalecer memória de longo prazo e recuperação de contexto por sessão

## P2 — Ecossistema

- Melhorar experiência de skills do usuário (discovery, execução, diagnóstico)
- Evoluir integração MCP e providers especializados
- Publicar guias de operação e release mais objetivos para deploy pessoal

## Critério mínimo por release

1. `pytest -q` passando
2. CLI principal sem regressão (`start`, `run`, `onboard`, `cron`, `skills`)
3. API principal funcionando (`/health`, `/v1/chat`, `/v1/cron/*`)
4. Documentação alinhada com o comportamento real

## ClawLite Parity Roadmap (nanobot + OpenClaw)

### NOW (Critical parity)
- [x] Replace passive channel stubs with active outbound adapters for Discord, Slack, and WhatsApp.
- [x] Enforce stronger tool safety policy for exec, web, and mcp.
- [x] Align gateway with production-grade contract.
- [x] Upgrade heartbeat to HEARTBEAT_OK + persisted check state.
- Progresso 2026-03-04: camada de compatibilidade do gateway entregue (`/api/status`, `/api/message`, `/api/token`, `/ws`, `/`).
- Progresso 2026-03-04: auth do gateway agora aplica hardening automatico (`off` -> `required`) em host nao-loopback quando token esta configurado; fallback de env legado `CLAWLITE_GATEWAY_TOKEN` suportado.
- Progresso 2026-03-04: contrato HTTP do gateway estabilizado com metadata (`contract_version`, `server_time`, `generated_at`, `uptime_s`), envelope de erro com `code`, e alias `/api/diagnostics` com paridade de `/v1/diagnostics`.
- Progresso 2026-03-04: heartbeat agora persiste check-state explícito com migração backward-compatible e escrita atômica fail-soft.
- Progresso 2026-03-04: ToolRegistry agora aplica política centralizada por canal para tools de risco (`exec`, `web_fetch`, `web_search`, `mcp`) com erro determinístico `tool_blocked_by_safety_policy:<tool>:<channel>`.
- Progresso 2026-03-04: Discord/Slack/WhatsApp agora têm envio outbound ativo com `httpx` (sem loops inbound neste incremento).

### NEXT (Operational maturity)
- [ ] Improve prompt/memory pipeline.
- [ ] Expand provider + config capability.
- [ ] Align workspace/bootstrap/templates with runtime lifecycle.
- [ ] Expand CLI operations.
- [ ] Add structured observability.

### FUTURE (Scale + polish)
- [ ] Subagent orchestration controls.
- [ ] Memory/session retention and compaction.
- [ ] Multi-channel concurrency optimization.
