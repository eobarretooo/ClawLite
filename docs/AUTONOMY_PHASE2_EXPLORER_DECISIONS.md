# ClawLite - Phase 2 Explorer Decisions (Itens 2-9)

Objetivo deste documento: registrar, antes de qualquer implementação, como OpenClaw e nanobot resolvem cada problema de autonomia e qual sera a adaptacao no ClawLite mantendo a arquitetura propria.

## Item 2 - Scheduler cron com loop automatico no startup

### Problema que OpenClaw + nanobot resolvem

Sem loop de scheduler em runtime, jobs cron existem no storage mas nao disparam sozinhos. Isso quebra automacao 24/7.

### Como o OpenClaw resolve

- `openclaw/src/cron/service.ts` e `openclaw/src/cron/service/ops.ts`
- `openclaw/src/cron/service/timer.ts`
- `openclaw/src/gateway/server-cron.ts`

Padrao chave:
- inicializa servico no bootstrap do gateway;
- recomputa proximo run, arma timer, executa jobs due;
- rearma timer apos cada tick;
- recupera estado no startup e trata jobs interrompidos.

### Como o nanobot valida o padrao

- `nanobot/cron/service.py`
- `nanobot/cli/commands.py` (gateway start)

Padrao chave:
- `cron.start()` chamado no startup do gateway;
- timer task assincrona com rearmamento continuo;
- callback de execucao do job injeta resultado no fluxo do agente.

### Proposta para ClawLite (arquitetura propria)

- Criar servico dedicado de scheduler em `clawlite/runtime/` para executar `run_cron_jobs()` periodicamente.
- Iniciar no lifecycle do gateway (startup) e parar no shutdown.
- Evitar overlap de execucoes (lock interno).
- Configuracao de intervalo via `gateway.cron_poll_interval_s`.

---

## Item 3 - Subagente como tool nativa no loop principal

### Problema que OpenClaw + nanobot resolvem

Sem tool nativa de subagente, o agente principal nao delega tarefas longas/paralelas sem bloquear o fluxo principal.

### Como o OpenClaw resolve

- `openclaw/src/agents/tools/sessions-spawn-tool.ts`
- `openclaw/src/agents/tools/subagents-tool.ts`
- `openclaw/src/agents/subagent-registry.ts`

Padrao chave:
- spawn via tool;
- registry de runs;
- controle de ciclo de vida (listar, matar, steer/restart);
- retorno assinado ao agente pai.

### Como o nanobot valida o padrao

- `nanobot/agent/subagent.py`
- `nanobot/agent/tools/spawn.py`
- `nanobot/agent/loop.py`

Padrao chave:
- `spawn` registrado como tool default;
- run em background task;
- callback de conclusao publica resultado de volta para canal do requester.

### Proposta para ClawLite (arquitetura propria)

- Adicionar runtime de subagentes em `clawlite/runtime/` com registry de runs.
- Expor tool nativa no `core/agent.py` (ex.: `spawn_subagent`, `subagents_list`, `subagents_kill`).
- Cada subagente executa tarefa isolada e devolve resultado proativo para a sessao origem.
- Integrar cancelamento por sessao para suportar `/stop`.

---

## Item 4 - Heartbeat com decisao skip/run + entrega proativa multi-canal

### Problema que OpenClaw + nanobot resolvem

Heartbeat baseado em token textual fixo (ex.: `HEARTBEAT_OK`) e entrega limitada a um canal cria falso positivo/negativo e baixa cobertura proativa.

### Como o OpenClaw resolve

- `openclaw/src/infra/heartbeat-runner.ts`
- `openclaw/src/infra/heartbeat-wake.ts`

Padrao chave:
- heartbeat com decisao controlada;
- wake explicit;
- entrega outbound alinhada ao alvo configurado/ativo.

### Como o nanobot valida o padrao

- `nanobot/heartbeat/service.py`
- `nanobot/cli/commands.py`

Padrao chave:
- fase 1: decisao estruturada (`skip`/`run`);
- fase 2: executa somente quando `run`;
- notifica canal ativo selecionado dinamicamente.

### Proposta para ClawLite (arquitetura propria)

- Evoluir `clawlite/core/heartbeat.py` para fluxo em 2 fases:
  - decisao estruturada;
  - execucao somente quando necessario.
- Substituir envio exclusivo Telegram por entrega proativa via `ChannelManager` para instancias/canais ativos.
- Manter compatibilidade com estado persistido (`heartbeat-state.json`).

---

## Item 5 - Sessao com manager dedicado por canal

### Problema que OpenClaw + nanobot resolvem

Sem camada dedicada de sessao por canal, fica dificil rastrear estado, tasks ativas, ultimo alvo de entrega e isolamento por origem.

### Como o OpenClaw resolve

- Estrutura de sessao com chave canonica por contexto e agente (familia `config/sessions`, `routing/session-key`).

Padrao chave:
- sessao como entidade de runtime (nao so string);
- mapeamento consistente entre canal/chat/thread e estado.

### Como o nanobot valida o padrao

- `nanobot/session/manager.py`
- `nanobot/agent/loop.py`

Padrao chave:
- `SessionManager` dedicado;
- cache + persistencia por chave (`channel:chat_id`);
- historia e metadados por sessao.

### Proposta para ClawLite (arquitetura propria)

- Criar `SessionManager` de runtime separado de `session_memory.py`, focado em:
  - bind de sessao por canal/instancia;
  - rastreamento de tasks ativas por sessao;
  - alvo preferencial para proactive send;
  - metadados por canal.

---

## Item 6 - Comando /stop para cancelar task sem derrubar processo

### Problema que OpenClaw + nanobot resolvem

Sem cancelamento por sessao, comandos longos continuam em execucao, piorando UX e consumo de recursos.

### Como o OpenClaw resolve

- `openclaw/src/gateway/chat-abort.ts`
- `openclaw/src/auto-reply/reply/commands-session-abort.ts`

Padrao chave:
- mapa de runs por sessao;
- abort por run/session key;
- resposta de estado abortado sem encerrar processo.

### Como o nanobot valida o padrao

- `nanobot/agent/loop.py` (`/stop`)

Padrao chave:
- cancela tasks ativas da sessao + subagentes da sessao;
- retorna feedback de quantas tasks foram interrompidas.

### Proposta para ClawLite (arquitetura propria)

- Interpretar `/stop` no roteador de mensagens dos canais.
- Cancelar tasks in-flight da sessao e subagentes associados.
- Retornar resposta padronizada de cancelamento.
- Nao interromper processo gateway/canal.

---

## Item 7 - MessageBus desacoplando canais do core

### Problema que OpenClaw + nanobot resolvem

Acoplamento direto canal->core torna dificil escalar, observar fila, tratar retry/fallback e manter fluxo proativo.

### Como o OpenClaw resolve

- Gateway/eventos com roteamento desacoplado por eventos internos.

Padrao chave:
- fronteira clara entre entrada de canal e processamento de agente.

### Como o nanobot valida o padrao

- `nanobot/bus/events.py`
- `nanobot/bus/queue.py`
- `nanobot/channels/manager.py`

Padrao chave:
- `InboundMessage` e `OutboundMessage` tipados;
- filas async separadas;
- dispatcher outbound dedicado.

### Proposta para ClawLite (arquitetura propria)

- Introduzir `MessageBus` em `clawlite/runtime/` com:
  - fila inbound;
  - fila outbound;
  - worker(s) de processamento;
  - request-reply para fluxo reativo.
- `ChannelManager` passa a publicar/consumir via bus, removendo acoplamento direto com `run_task_with_meta`.

---

## Item 8 - Memoria com consolidacao automatica no fim da sessao

### Problema que OpenClaw + nanobot resolvem

Sem consolidacao ao encerrar sessao, contexto cresce sem curadoria e perde sinal util no longo prazo.

### Como o OpenClaw resolve

- Consolidacao e manutencao de contexto por ciclo de sessao/turno.

### Como o nanobot valida o padrao

- `nanobot/agent/memory.py`
- `nanobot/session/manager.py`
- `nanobot/agent/loop.py`

Padrao chave:
- consolidacao periodica ou por transicao de sessao;
- persistencia em artefatos de memoria longa + historico resumido.

### Proposta para ClawLite (arquitetura propria)

- Acrescentar gatilho de consolidacao ao encerramento de sessao (`/stop` e idle timeout).
- Reaproveitar `session_memory.save_session_summary` e `compact_daily_memory`.
- Garantir idempotencia (nao consolidar repetido na mesma janela curta).

---

## Item 9 - Skills com auto-descoberta via SKILL.md (always + requires)

### Problema que OpenClaw + nanobot resolvem

Catalogo estatico de skills limita extensibilidade e impede carregar automaticamente skills de workspace/marketplace com metadados de ativacao.

### Como o OpenClaw resolve

- `openclaw/src/agents/skills/workspace.ts`
- `openclaw/src/agents/skills/frontmatter.ts`

Padrao chave:
- discovery por filesystem;
- parsing de frontmatter;
- politicas de invocacao;
- campos `always` e `requires` para elegibilidade.

### Como o nanobot valida o padrao

- `nanobot/agent/skills.py`

Padrao chave:
- scan em workspace + builtin;
- parse de frontmatter;
- filtro por requirements (`bins`, `env`);
- lista de always skills.

### Proposta para ClawLite (arquitetura propria)

- Criar loader de descoberta em `clawlite/skills/`:
  - scan de skills instaladas/local workspace por `SKILL.md`;
  - parse de `always` e `requires`;
  - filtro de disponibilidade.
- Integrar no contexto do agente (resumo de skills disponiveis + always carregadas).
- Manter compatibilidade com `skills/registry.py` para ferramentas existentes (MCP/configure).

---

## Ordem de implementacao aprovada para fase 2

1. Item 2 - Scheduler cron auto-start
2. Item 3 - Tool nativa de subagente
3. Item 4 - Heartbeat skip/run + proactive multi-canal
4. Item 5 - Session manager dedicado por canal
5. Item 6 - `/stop` com cancelamento por sessao
6. Item 7 - MessageBus
7. Item 8 - Consolidacao de memoria no fim de sessao
8. Item 9 - Auto-discovery de skills via `SKILL.md`

Nota: a ordem segue impacto operacional imediato + dependencia tecnica entre itens.
