# Dashboard Web do ClawLite (MVP)

Painel web integrado ao Gateway FastAPI para operação local estilo OpenClaw.

## Acesso

- URL: `http://<host>:<port>/dashboard`
- Auth: token do gateway (`~/.clawlite/config.json -> gateway.token`)

## Entregas do MVP

1. **Autenticação por token**
   - `POST /api/dashboard/auth`
   - Header `Authorization: Bearer <token>` nas rotas protegidas
   - WebSocket protegido por `?token=<token>`

2. **Chat em tempo real (WebSocket)**
   - `GET ws://.../ws/chat?token=...`
   - Mensagem: `{"type":"chat","session_id":"...","text":"..."}`
   - Resposta: `{"type":"chat","message":{...}}`

3. **Status gateway**
   - `GET /api/dashboard/status`
   - inclui online, uptime, modelo e conexões

4. **Skills manager**
   - `GET /api/dashboard/skills`
   - `POST /api/dashboard/skills/install`
   - `POST /api/dashboard/skills/enable`
   - `POST /api/dashboard/skills/disable`
   - `POST /api/dashboard/skills/remove`

5. **Histórico de sessões com busca**
   - `GET /api/dashboard/sessions?q=<texto>`
   - `GET /api/dashboard/sessions/{session_id}`

6. **Monitor de tokens/custos (estimado localmente)**
   - `GET /api/dashboard/telemetry`
   - dados persistidos em `~/.clawlite/dashboard/telemetry.jsonl`

7. **Configurações visuais/operacionais**
   - `GET /api/dashboard/settings`
   - `PUT /api/dashboard/settings` (model/channels/hooks/theme)

8. **Logs em tempo real**
   - `GET /api/dashboard/logs`
   - `GET ws://.../ws/logs?token=...`

9. **Dark mode + responsivo mobile**
   - UI em `clawlite/gateway/dashboard.html`
   - sem frameworks pesados

## Persistência local

- `~/.clawlite/dashboard/sessions.jsonl`
- `~/.clawlite/dashboard/telemetry.jsonl`
- `~/.clawlite/dashboard/settings.json`

## Observações

- Chat no MVP usa **stub local** para resposta do assistente (sem provedor externo).
- Custos/tokens são estimados (heurística simples), não billing oficial.
