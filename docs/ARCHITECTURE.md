# Architecture

Arquitetura atual (runtime novo), sem legado:

```text
clawlite/
├── core/         # engine, prompt, memory, skills, subagent
├── tools/        # tool abc, registry e tools builtin
├── bus/          # eventos e fila assíncrona
├── channels/     # manager + canais (telegram completo, demais adapters)
├── gateway/      # FastAPI + WebSocket
├── scheduler/    # cron + heartbeat
├── providers/    # litellm/custom/codex/transcription
├── session/      # store JSONL por sessão
├── config/       # schema + loader
├── workspace/    # loader + templates de identidade
├── skills/       # skills markdown builtin (SKILL.md)
├── cli/          # comandos start/run/onboard/cron
└── utils/        # helpers compartilhados
```

## Fluxo principal

1. Mensagem entra por `channels` ou `gateway`.
2. `core.engine` monta prompt (workspace + memória + histórico + skills).
3. Provider responde; se houver tool calls, `tools.registry` executa.
4. Resposta final é persistida em `session.store` e consolidada em `core.memory`.
5. `scheduler.cron` e `scheduler.heartbeat` disparam execuções proativas.
