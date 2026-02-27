# Dashboard Web do ClawLite (v2)

Painel web integrado ao Gateway FastAPI para operacao local do agente.

## Acesso

- URL: `http://<host>:<port>/dashboard`
- Auth: token do gateway (`~/.clawlite/config.json -> gateway.token`)

## Principais entregas da v2

1. **Chat conectado ao pipeline real do agente**
   - `WS /ws/chat?token=<token>`
   - Mensagem enviada:
     - `{"type":"chat","session_id":"...","text":"..."}`
   - Mensagem recebida:
     - `{"type":"chat","message":{...},"meta":{...},"telemetry":{...}}`
   - `meta` inclui `mode`, `reason` e `model` retornados pelo pipeline.
   - Hooks `pre/post` salvos em settings sao aplicados no prompt/resposta.

2. **Telemetria de tokens/custo por sessao e periodo**
   - `GET /api/dashboard/telemetry`
   - Query params:
     - `session_id` (opcional)
     - `period` (`24h`, `7d`, `30d`, `today`, `week`, `month`, `all`)
     - `granularity` (`auto`, `hour`, `day`)
     - `start`, `end` (ISO8601; opcionais)
     - `limit` (1..500, default 200)
   - Resposta inclui:
     - `summary` (eventos, sessoes, prompt/completion/total tokens, custos)
     - `sessions` (agregado por sessao)
     - `timeline` (agregado por bucket de tempo)
     - `events` (eventos filtrados recentes)

3. **Acoes de skills com feedback**
   - `GET /api/dashboard/skills`
   - `POST /api/dashboard/skills/install`
   - `POST /api/dashboard/skills/enable`
   - `POST /api/dashboard/skills/disable`
   - `POST /api/dashboard/skills/remove`
   - Frontend mostra loading/sucesso/erro por acao.

4. **Logs realtime com filtros basicos e busca**
   - `GET /api/dashboard/logs?limit=...&level=...&event=...&q=...`
   - `WS /ws/logs?token=<token>&level=...&event=...&q=...`
   - Filtros tambem podem ser atualizados via websocket:
     - `{"type":"filters","level":"...","event":"...","q":"..."}`

5. **Persistencia local**
   - `~/.clawlite/dashboard/sessions.jsonl`
   - `~/.clawlite/dashboard/telemetry.jsonl`
   - `~/.clawlite/dashboard/settings.json`

## Endpoints auxiliares

- `POST /api/dashboard/auth`
- `GET /api/dashboard/bootstrap`
- `GET /api/dashboard/status`
- `GET /api/dashboard/sessions?q=<texto>`
- `GET /api/dashboard/sessions/{session_id}`
- `GET /api/dashboard/settings`
- `PUT /api/dashboard/settings`

## Observacoes

- A estimativa de custo e local (heuristica por modelo), nao e billing oficial.
- Para monitorar eventos em tempo real, mantenha o websocket de logs conectado.
