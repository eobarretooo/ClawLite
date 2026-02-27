# ClawLite — Plano de Produção v1 (7 dias)

Objetivo: levar o ClawLite para produção com operação contínua, segurança e cadência de evolução.

## Dia 1-2 — P0 Produção
- Hardening de canais (retry, rate-limit, reconexão automática em Telegram/Slack/Discord/WhatsApp/Teams)
- Secrets management (.env + suporte vault + rotação de tokens)
- Backup/restore automático de:
  - `~/.clawlite/multiagent.db`
  - `~/.clawlite/learning.db`
  - `~/.clawlite/config.json`
  - `~/.clawlite/workspace/`

## Dia 2-3 — P0 Qualidade
- Pipeline CI completo (unit + integration + e2e + secret scan + lint + type-check)
- Smoke test pós-deploy (`doctor/status/start/ws/chat`)
- Versionamento semântico + changelog automático

## Dia 3-4 — P0 Observabilidade
- Métricas: erro, latência, fila, worker down
- Alertas automáticos no Telegram
- Runbook de incidentes (gateway down, channel auth, DB lock)

## Dia 4-5 — P1 Dashboard parity
- Cron completo no UI
- Channels panel completo
- Config avançada + apply/restart
- Debug/update panel

## Dia 5-6 — P1 Multi-agente
- Finalizar `agents create/list/bind` multi-canal
- Menção + handoff + orquestrador em todos os canais
- Testes de carga + soak test real 30 min

## Dia 6-7 — P1 Segurança + Operação contínua
- Política de permissões por agente/canal
- Auditoria de ações sensíveis
- Isolamento de sessão
- Cron interno de manutenção diário/semanal
- Aprovação: low-risk auto-merge / high-risk requer OK
- Cadência release: patch semanal (`v0.4.x`), minor quinzenal (`v0.5.x`)

## Definição de pronto
1. Uptime estável + reconexão automática ✅
2. Testes e smoke 100% no CI ✅
3. Backup/restore validado ✅
4. Observabilidade com alertas ✅
5. Runbook + rollback funcionando ✅
