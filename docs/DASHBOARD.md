# ClawLite Dashboard (Control UI)

Web dashboard embutido no gateway FastAPI para operar o ClawLite no estilo do OpenClaw Control UI.

## Acesso

- URL: `http://<host>:<port>/dashboard`
- Token: `~/.clawlite/config.json` (`gateway.token`)
- A URL aceita `#token=<TOKEN>` para login rapido.

## Abas disponiveis

1. `Overview`
   - status geral, uptime, conexoes;
   - metrics de workers/tasks/log ring;
   - snapshot de debug;
   - heartbeat status.

2. `Chat`
   - websocket streaming em tempo real (`/ws/chat`);
   - mensagens com metadados (`mode`, `reason`, `model`);
   - carga de historico por `session_id`.

3. `Sessions`
   - busca de sessoes;
   - inspecao de mensagens por sessao;
   - envio da sessao selecionada para a aba de chat.

4. `Telemetry`
   - resumo de eventos/tokens/custo;
   - ranking por sessao;
   - timeline por bucket;
   - eventos recentes.

5. `Channels`
   - status/configuracao de canais;
   - instancias ativas;
   - reconnect por canal;
   - pairing pendente/aprovado (approve/reject).

6. `Cron`
   - criar/atualizar jobs;
   - listar jobs correntes;
   - remover jobs.

7. `Config`
   - model/hook/theme;
   - edicao do bloco `channels` em JSON;
   - save settings;
   - dry-run/apply config;
   - restart request (safe/noop no runtime embutido).

8. `Workspace`
   - editor para `SOUL.md`, `USER.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`.

9. `Skills`
   - listar skills locais (enable/disable/remove);
   - instalar skill local por slug;
   - update dry-run/apply;
   - leitura do manifesto do hub.

10. `Agents`
    - listar agentes e bindings;
    - criar agente;
    - bind de agente por canal/conta.

11. `Logs`
    - stream realtime com filtros (`/ws/logs`);
    - fallback pull (`/api/dashboard/logs`).

12. `Security`
    - mapa de roles/scopes;
    - politicas de ferramenta (`allow/review/deny`);
    - trilha de auditoria de ferramentas.

## Endpoints usados

- Auth/boot: `POST /api/dashboard/auth`, `GET /api/dashboard/bootstrap`, `GET /api/dashboard/status`
- Health/metrics: `GET /health`, `GET /api/metrics`, `GET /api/dashboard/debug`, `GET /api/heartbeat/status`
- Chat/log streams: `WS /ws/chat`, `WS /ws/logs`
- Sessions: `GET /api/dashboard/sessions`, `GET /api/dashboard/sessions/{session_id}`
- Telemetry: `GET /api/dashboard/telemetry`
- Channels/pairing: `GET /api/channels/status`, `GET /api/channels/instances`, `POST /api/channels/reconnect`,
  `GET /api/pairing/pending`, `GET /api/pairing/approved`, `POST /api/pairing/approve`, `POST /api/pairing/reject`
- Cron: `GET /api/cron`, `POST /api/cron`, `DELETE /api/cron/{job_id}`
- Config/models: `GET /api/dashboard/settings`, `PUT /api/dashboard/settings`, `POST /api/dashboard/config/apply`,
  `POST /api/dashboard/config/restart`, `GET /api/models/catalog`
- Workspace: `GET /api/workspace/file`, `PUT /api/workspace/file`
- Skills/hub/update: `GET /api/dashboard/skills`, `POST /api/dashboard/skills/install`,
  `POST /api/dashboard/skills/enable`, `POST /api/dashboard/skills/disable`,
  `POST /api/dashboard/skills/remove`, `POST /api/dashboard/update`,
  `GET /api/hub/manifest`
- Agents: `GET /api/agents`, `POST /api/agents`, `POST /api/agents/bind`
- Security: `GET /api/security/rbac`, `PUT /api/security/tool-policy`, `GET /api/security/tool-audit`

## Notas

- Custo em telemetry e estimado localmente, nao billing oficial.
- Quando usar token em URL, prefira `#token=` (fragmento) para reduzir exposicao em logs/proxies.
