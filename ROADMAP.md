# ClawLite Roadmap

Roadmap para consolidar o ClawLite como assistente pessoal de produção, com foco em segurança, operação contínua e UX.

## Horizonte atual

### P0 — Base estável

- Robustez de canais (retry, reconexão, rate-limit)
- Onboarding/configure com fluxo claro e seguro
- Backup/restore confiável do estado local
- CI com testes e secret scan obrigatórios

### P1 — Operação de assistente pessoal

- Melhorias de pairing e allowlist por canal
- Observabilidade operacional (status, alertas, health checks)
- Workflows de daemon mais simples para Linux/Termux
- Runbook de incidentes com recuperação rápida

### P2 — Evolução de capacidade

- Mais skills de produtividade pessoal
- Melhorias de memória e recuperação de contexto
- Integrações MCP adicionais para ferramentas externas
- Dashboard com paridade de operações avançadas

## Critérios de pronto por release

1. Testes passando em CI
2. Sem regressão em `doctor`, `onboarding`, `start`
3. Documentação atualizada para mudanças de comportamento
4. Migração/configuração backward compatible
5. Risco operacional documentado no changelog
