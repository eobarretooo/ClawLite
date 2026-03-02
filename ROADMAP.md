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
