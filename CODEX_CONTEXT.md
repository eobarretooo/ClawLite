# CODEX_CONTEXT.md

## Projeto

O **ClawLite** e um assistente pessoal de IA local-first, inspirado no OpenClaw, reimplementado em Python com foco em autonomia real (24/7), canais persistentes, memoria, cron e operacao em Linux/Termux.

Objetivo pratico do projeto:
- atingir autonomia operacional 20/20 (daemon, memoria, canais, cron, ferramentas, subagentes, recover)
- manter arquitetura propria do ClawLite, usando OpenClaw/nanobot como referencia de padrao
- manter compatibilidade forte com Termux + proot Ubuntu

Stack principal:
- Python 3.10+
- FastAPI + WebSocket
- asyncio
- SQLite (multiagent/memory)
- Termux + proot Ubuntu (deploy mobile)

## Referências

- **OpenClaw** (fonte da verdade funcional): `/root/projetos/openclaw` (TypeScript)
- **nanobot** (validacao de padroes de autonomia): `/root/projetos/nanobot` (Python)
- Skills usadas com frequencia nesta trilha:
  - `$ts-to-python`
  - `$openclaw-analyzer`
  - `$clawlite-porter`
  - `$async-python-patterns`

## Status atual

- Autonomia: **19/20** (boot automático pendente — futuro app Android)
- Testes: **264 passando** (`pytest -q`)
- Linha de commits de referencia consolidada ate: **`b0f23d5`**
- Estado recente de daemon/autostart:
  - `supervisord` configurado em `/root/.clawlite/supervisord.conf`
  - fluxo de boot script (`~/.termux/boot/clawlite-supervisord.sh`) removido
  - `clawlitex autostart` agora configura apenas o `supervisord` no proot
  - inicializacao atual do gateway: manual (`clawlitex start` no Termux)
  - boot automático permanece pendente de app Android dedicado (futuro)

## Atualizacoes de hoje (2026-03-01)

- Skills autoload executaveis via `SKILL.md` implementadas e funcionando:
  - novo `SKILL.md` com `command:` ou `script:` vira tool executavel sem editar `registry.py`
  - fallback dinamico no dispatch MCP preservando compatibilidade com skills estaticas
- Diretórios de skills alinhados:
  - builtin: `repo/skills`
  - runtime usuario: `~/.clawlite/workspace/skills`
  - marketplace: `~/.clawlite/marketplace/skills`
- Criacao automatica dos diretorios runtime de skills no discovery/workspace.
- Exemplos de skill runtime criados:
  - `~/.clawlite/workspace/skills/git-operations/SKILL.md` (`always: true`)
  - `~/.clawlite/workspace/skills/code-analysis/SKILL.md` (`always: false`, `script: run.py`)
- Templates de identidade ricos com placeholders implementados:
  - `IDENTITY.md`, `SOUL.md`, `USER.md`, `AGENTS.md`, `TOOLS.md` com placeholders `{{...}}`
  - defaults sensatos quando onboarding nao foi rodado
  - `onboarding.py` preenchendo os templates com dados do wizard
- Testes adicionados/atualizados para autoload dinamico e templates:
  - `tests/test_dynamic_skill_autoload.py`
  - `tests/test_onboarding_rich_templates.py`
  - suite completa verde: `264 passed`
- Autostart/boot no Termux:
  - geracao de `~/.termux/boot/clawlite-supervisord.sh` removida do `clawlitex`
  - docs atualizadas para fluxo manual de start no Termux

## Arquitetura do ClawLite

Modulos principais:

- `clawlite/gateway/`
  - servidor FastAPI, WebSocket, dashboard e rotas HTTP
  - arquivos chave:
    - `/root/projetos/ClawLite/clawlite/gateway/server.py`
    - `/root/projetos/ClawLite/clawlite/gateway/routes/channels.py`
    - `/root/projetos/ClawLite/clawlite/gateway/routes/cron.py`
    - `/root/projetos/ClawLite/clawlite/gateway/routes/workspace.py`

- `clawlite/channels/`
  - conectores de canais (telegram, slack, discord, googlechat, irc, signal, imessage etc.)
  - manager central de canais, outbound resiliente, pairing
  - arquivos chave:
    - `/root/projetos/ClawLite/clawlite/channels/manager.py`
    - `/root/projetos/ClawLite/clawlite/channels/telegram.py`
    - `/root/projetos/ClawLite/clawlite/channels/outbound_resilience.py`

- `clawlite/core/`
  - loop do agente, chamada de modelo, tools locais, heartbeat
  - arquivos chave:
    - `/root/projetos/ClawLite/clawlite/core/agent.py`
    - `/root/projetos/ClawLite/clawlite/core/heartbeat.py`

- `clawlite/runtime/`
  - runtime operacional: cron, memoria de sessao, multiagent, message bus, status, update
  - arquivos chave:
    - `/root/projetos/ClawLite/clawlite/runtime/conversation_cron.py`
    - `/root/projetos/ClawLite/clawlite/runtime/multiagent.py`
    - `/root/projetos/ClawLite/clawlite/runtime/message_bus.py`
    - `/root/projetos/ClawLite/clawlite/runtime/session_memory.py`
    - `/root/projetos/ClawLite/clawlite/runtime/self_update.py`

- `clawlite/skills/`
  - implementacoes de skills nativas
- `skills/`
  - catalogo de SKILL.md para descoberta/compatibilidade

Docs e operacao:
- `/root/projetos/ClawLite/docs/TERMUX_PROOT_AUTOSTART.md`
- `/root/projetos/ClawLite/docs/RUNBOOK.md`
- `/root/projetos/ClawLite/README.md`

## O que foi feito (10 commits principais)

1. `41017ea` - `docs(autonomy)`  
   Registrou decisoes de portagem/autonomia (explorer phase2).

2. `e57f449` - `feat(cron-scheduler)`  
   Iniciou loop automatico do scheduler cron no startup do gateway.

3. `e6ec462` - `feat(subagents)`  
   Adicionou tools nativas de subagentes no loop principal do agente.

4. `4419033` - `feat(heartbeat)`  
   Fluxo de decisao skip/run no heartbeat + entrega proativa multicanal.

5. `785b23d` - `feat(channel-sessions)`  
   Session manager dedicado por canal.

6. `7e302c8` - `feat(stop-command)`  
   `/stop` cancela task em execucao sem derrubar o processo.

7. `926cfff` - `feat(message-bus)`  
   Desacoplou entrada de canais do core via MessageBus.

8. `56b2ca0` - `feat(memory-consolidation)`  
   Consolidacao/sumarizacao automatica de memoria ao fim da sessao.

9. `7391457` - `feat(skill-discovery)`  
   Descoberta de `SKILL.md` com metadados (`always`/`requires`) no runtime.

10. `7878b6f` - `feat(subagents-delivery)`  
    Resultado de subagente publicado de volta no canal de origem.

## Bloqueador restante para 20/20

1. **Boot automático Android**  
   Pendente de app Android dedicado para iniciar o gateway sem abrir o Termux.

## Proximos passos (ordem)

1. Internacionalizacao (pt-BR -> English).
2. App Android para boot automático e fechamento de 20/20.
3. Auto-desenvolvimento controlado.
4. Integracao com ClawWork.

## Como retomar

1. Ler este arquivo primeiro: `/root/projetos/clawlite/CODEX_CONTEXT.md`
2. Ver historico recente:
   - `cd /root/projetos/ClawLite`
   - `git log --oneline -15`
3. Confirmar estado tecnico:
   - `pytest -q`

Sequencia recomendada apos retomada:
- iniciar internacionalizacao (pt-BR -> English)
- especificar app Android de boot automático (escopo, permissões, lifecycle)
- validar ciclo 24/7 com `supervisord` + start manual no Termux
- fechar bloqueador restante para migrar de 19/20 para 20/20
