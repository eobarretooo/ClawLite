# 🤖 Multi-agente

Crie e controle workers para execução paralela por canal/label.

## Registrar e iniciar worker

```bash
clawlite agents register \
  --channel telegram \
  --chat-id 1850513297 \
  --label general \
  --command-template 'clawlite run "{text}"'

clawlite agents start --worker-id 1
```

## Operação

```bash
clawlite agents list
clawlite agents recover
clawlite agents stop --worker-id 1
```

:::warning
Use `recover` em incidentes de processo para restabelecer workers automaticamente.
:::

➡️ Próxima página: [FAQ](/faq)
