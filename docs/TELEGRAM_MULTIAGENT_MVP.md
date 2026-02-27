# Telegram Multi-Agent MVP (P0)

## Escopo entregue

MVP funcional sem dependência de Discord com:

1. **Gerenciador de workers persistentes por chat/thread**
   - Estado em SQLite (`~/.clawlite/multiagent.db`)
   - Tabela `workers` com chave única `(channel, chat_id, thread_id, label)`
   - Controle de ciclo de vida (`register`, `start`, `stop`, `list`)
2. **Roteamento para subagentes locais por label**
   - Tabela `tasks` com fila persistente
   - Dispatch por `(channel, chat_id, thread_id, label)`
   - Worker executa `command_template` com placeholders (`{text}`, `{label}`, `{chat_id}`, `{thread_id}`, `{channel}`)
3. **CLI de gerenciamento**
   - `clawlite agents register`
   - `clawlite agents start|stop|list|recover`
   - `clawlite agents tasks`
   - `clawlite agents worker --worker-id N` (loop de execução)
4. **Integração mínima Telegram**
   - Template novo: `clawlite channels template telegram-multiagent`
   - Dispatch local: `clawlite agents telegram-dispatch --config ...`
5. **Recuperação automática pós-restart**
   - `recover_workers()` chamado automaticamente antes de `list/start/tasks/telegram-dispatch`
   - Workers `enabled=1` sem PID válido são religados

## Arquitetura

- `clawlite/runtime/multiagent.py`
  - DB init, CRUD de worker, loop de worker, fila de tasks, recover
- `clawlite/runtime/telegram_multiagent.py`
  - Template Telegram multiagente + dispatch local
- `clawlite/cli.py`
  - Novo namespace `agents`

## Fluxo básico

1. Registrar worker para um chat/thread/label
2. Subir worker (`start`) — processo desacoplado via `subprocess.Popen`
3. Enfileirar task (dispatch local)
4. Worker consome task, executa comando local e grava resultado em SQLite
5. Após restart da máquina/processo, `recover_workers()` restaura workers ativos

## Exemplo rápido

```bash
# gerar template
clawlite channels template telegram-multiagent > telegram.multiagent.json

# registrar worker
clawlite agents register \
  --channel telegram \
  --chat-id 123456 \
  --thread-id suporte \
  --label general \
  --cmd 'clawlite run "{text}"'

# iniciar worker id 1
clawlite agents start 1

# disparar task
clawlite agents telegram-dispatch \
  --config telegram.multiagent.json \
  --chat-id 123456 \
  --thread-id suporte \
  --label general \
  "resuma os próximos passos"

# acompanhar
clawlite agents tasks
```

## Limitações conhecidas (MVP)

- Não há ACK de envio de resposta ao Telegram (somente dispatch local + execução local)
- Execução usa `shell=True` no template (válido para MVP, requer hardening posterior)
- Não existe priorização/retry/backoff por task
- Não existe isolamento de runtime por worker (mesmo host/process namespace)
