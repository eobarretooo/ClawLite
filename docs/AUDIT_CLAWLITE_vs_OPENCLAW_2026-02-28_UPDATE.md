# AUDIT UPDATE: ClawLite vs OpenClaw (2026-02-28)

## Escopo desta revisão
- Base analisada: `/root/projetos/ClawLite` (estado local atual).
- Referência comparativa: `/root/projetos/openclaw` (README e arquitetura geral).
- Objetivo: validar paridade real, corrigir gaps críticos e medir viabilidade de "ficar igual".

## Estado atual validado
- Suite de testes: `151 passed`.
- `run_remote_provider` não é mais stub (há chamada real via `httpx` para OpenAI/Anthropic/OpenRouter).
- Streaming está implementado (`runtime/streaming.py`, `gateway/chat.py`, `routes/websockets.py`).
- Canais nativos existem em Python (`telegram`, `discord`, `slack`, `whatsapp`) via classes dedicadas.

## Correções aplicadas nesta rodada
1. Segurança no worker multiagente:
   - Removido `shell=True` em `runtime/multiagent.py`.
   - Introduzido parser seguro `_render_command_args(...)` com `shlex`.
   - Adicionado timeout explícito de execução para comandos de worker.

2. Multi-conta/canal no runtime:
   - `channels/manager.py` agora inicia múltiplas contas (`accounts`) por canal.
   - Passagem de parâmetros específicos por canal corrigida:
     - Slack: `app_token` + `allowFrom`
     - WhatsApp: `phone_number_id/phone` + `allowFrom`
     - Telegram/Discord: allowlist por configuração

3. Persistência de configuração de canais:
   - `gateway/routes/channels.py` deixou de perder campos importantes ao salvar/aplicar:
     - `accounts`, `allowFrom`, `app_token`, `phone_number_id`, campos STT/TTS e metadados por canal.
   - Status de canal agora inclui:
     - `instances_online`
     - `accounts_configured`

4. Webhook WhatsApp:
   - `gateway/routes/webhooks.py` agora resolve instância por `phone_number_id` (quando houver múltiplas contas).

5. Higiene do repositório:
   - Removidos artefatos de debug/versionamento acidental:
     - `deleteme2.tmp`
     - `traceback.txt`
     - `test_import.py`
     - `verify_sprint4.py`

## Testes adicionados
- `tests/test_multiagent_worker_security.py`
  - garante execução sem shell e sem injection via metacaracteres.
- `tests/test_channel_manager.py`
  - garante bootstrap de múltiplas contas e kwargs corretos por canal.
- `tests/test_cron_channels_metrics.py`
  - ampliado para validar persistência de `accounts` e `app_token` no endpoint de canais.

## Paridade com OpenClaw: leitura realista

### Onde já está próximo
- Wizard/onboarding CLI.
- Gateway HTTP + WebSocket com streaming.
- Runtime de memória/aprendizado.
- Marketplace/instalação de skills.
- MCP server/client básico.

### Onde ainda existe gap relevante
- Ecossistema: OpenClaw tem superfície muito maior (apps/nodes, mais canais/extensões).
- Operação de produção:
  - sem `install-daemon` nativo (systemd/launchd) no CLI principal.
  - sem camada de pairing/dispositivos equivalente.
- Segurança operacional avançada e runbooks no nível OpenClaw ainda incompletos.

### Onde há gap estrutural (não só código)
- OpenClaw inclui partes multiplataforma (macOS/iOS/Android nodes, canvas e integrações específicas).
- Reproduzir 1:1 em Python puro é possível só parcialmente; algumas peças dependem de stack e ecossistema diferentes.

## Veredito objetivo
- **É possível aproximar bastante o ClawLite do OpenClaw em comportamento de gateway/agent/canais.**
- **Paridade total 1:1 não é realista no curto prazo** sem expandir stack (incluindo partes na linguagem/ecossistema do OpenClaw) e investir em apps/nodes/plataformas.

## Próximos passos recomendados (prioridade)
1. `clawlite install-daemon` (systemd user service) + comando de status/restart.
2. Política de pairing/allowlist por canal com fluxo de aprovação explícito.
3. Painel de canais no dashboard com estado de conexão/reconexão por instância.
4. Hardening operacional: backup/restore oficial de `config + dbs`.
